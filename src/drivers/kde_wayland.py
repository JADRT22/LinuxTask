import subprocess
import time
import logging
import atexit
import os
import tempfile
import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib
import threading
import re
from evdev.ecodes import BTN_LEFT, BTN_MIDDLE, BTN_RIGHT

from .base import DesktopManager, FALLBACK_RESOLUTION

logger = logging.getLogger(__name__)

# evdev button code -> evdev button code: the RemoteDesktop portal spec
# wants evdev codes (272/273/274), not X11 button numbers 1/2/3.
BTN_MAP = {BTN_LEFT: 272, BTN_RIGHT: 273, BTN_MIDDLE: 274}

# KWin cursor read (kdotool mechanism): a one-shot KWin script reports
# workspace.cursorPos back to our private bus name. xdotool is frozen
# on KDE Wayland (XWayland only tracks the pointer over X surfaces),
# so this is the primary position source.
_KWIN_PROBE_NAME = 'org.linuxtask.cursorprobe'
_KWIN_SCRIPT_NAME = 'linuxtask_cursor_pos'
_KWIN_SCRIPT = (
    'var p = workspace.cursorPos;\n'
    'callDBus("%s", "/", "%s", "result", p.x+","+p.y);\n'
    % (_KWIN_PROBE_NAME, _KWIN_PROBE_NAME)
)

# Degrade after repeated read failures: KWin's replies never arriving
# (e.g. the GLib dispatch loop stopped) would stall every read for the
# full 2 s wait. After this many consecutive failures, skip KWin for
# _KWIN_SKIP_READS reads, then probe once; a success resets the streak.
_KWIN_FAIL_SKIP_AFTER = 3
_KWIN_SKIP_READS = 8


class _KwinCursorProbe(dbus.service.Object):
    """Receives the position KWin's script sends back via callDBus.

    Created AFTER the driver's GLib loop is running so incoming calls
    get dispatched. Each read resets the event/value buffer; reads are
    serialized by the driver's lock (one in-flight read at a time).
    """

    def __init__(self, bus):
        self._event = threading.Event()
        self._value = None
        super().__init__(conn=bus, object_path='/')

    @dbus.service.method(_KWIN_PROBE_NAME, in_signature='s',
                         out_signature='')
    def result(self, payload):
        self._value = str(payload)
        self._event.set()

    def reset(self):
        # ponytail: stale-reply window — if a read times out and KWin's
        # callDBus reply lands right after, the NEXT read could parse
        # that late reply instead of its own. Benign today: the payload
        # is still real compositor truth from a run that did execute
        # (at most a position from a few ms earlier). Upgrade path if it
        # ever matters: tag the payload with a per-read sequence number
        # and ignore mismatches.
        self._value = None
        self._event.clear()

    def wait(self, timeout):
        return self._event.wait(timeout)

    def payload(self):
        return self._value


class KdeWaylandDriver(DesktopManager):
    """KDE Wayland driver using Portal RemoteDesktop for cursor control."""

    def __init__(self):
        super().__init__()
        self._session_handle = None
        self._cur_x = 0
        self._cur_y = 0
        self._pos_initialized = False
        self._portal_ready = False
        self._dbus_loop = None
        self._bus = None
        # KWin cursor-read plumbing (lazily built in _kwin_read_setup,
        # after _portal_init has started the GLib loop below).
        self._kwin_ready = False
        self._kwin_lock = threading.Lock()
        self._kwin_probe = None
        self._kwin_scripting = None
        self._kwin_script_path = None
        self._kwin_atexit_registered = False
        self._kwin_last_error = None
        # Consecutive read failures / reads skipped by the degrade rule.
        self._kwin_fail_count = 0
        self._kwin_skip_count = 0
        # Optional UI hook: main injects it so a skipped event becomes a
        # visible notice instead of log-only silence.
        self.warn_fn = None
        self.screen_width = 0
        self.screen_height = 0
        self._detect_resolution()
        self._portal_init()

    def _detect_resolution(self):
        # Prefer kscreen-doctor (native Wayland); xrandr only mirrors
        # XWayland and may be absent. kscreen marks the active mode
        # with '*' and uses ANSI colors, so strip escapes first.
        try:
            out = subprocess.check_output(
                ['kscreen-doctor', '-o'],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode()
            out = re.sub(r'\x1b\[[0-9;]*m', '', out)
            for line in out.splitlines():
                # The active mode is the resolution immediately before
                # '*', e.g. '5:1600x900@59.95*'. A plain 'x' search would
                # grab the first mode on the line instead.
                m = re.search(r'(\d+)x(\d+)@[0-9.]*\*', line)
                if m:
                    self.screen_width = int(m.group(1))
                    self.screen_height = int(m.group(2))
                    logger.info(
                        "Resolution (kscreen): %dx%d",
                        self.screen_width, self.screen_height)
                    return
        except Exception as exc:
            logger.debug("kscreen-doctor failed: %s", exc)
        try:
            out = subprocess.check_output(
                ['xrandr'], stderr=subprocess.DEVNULL, timeout=2
            ).decode()
            for line in out.splitlines():
                if '*' in line:
                    m = re.search(r'(\d+)x(\d+)', line)
                    if m:
                        self.screen_width = int(m.group(1))
                        self.screen_height = int(m.group(2))
                        logger.info("Resolution: %dx%d",
                                    self.screen_width, self.screen_height)
                        return
        except Exception:
            logger.debug("xrandr fallback failed.", exc_info=True)
        self.screen_width, self.screen_height = FALLBACK_RESOLUTION
        logger.warning("Using fallback resolution: 1920x1080")

    def _predict_request_path(self, token):
        name = self._bus.get_unique_name().replace('.', '_').replace(':', '')
        return f"/org/freedesktop/portal/desktop/request/{name}/{token}"

    def _portal_call(self, method, *args, timeout=15):
        handle_token = f"ht_{int(time.time() * 1000000)}"
        request_path = self._predict_request_path(handle_token)
        event = threading.Event()
        result_container = []

        def response_callback(*resp_args):
            logger.debug("Portal response signal: %s", resp_args)
            result_container.append(resp_args)
            event.set()

        logger.debug("Subscribing to portal response on: %s", request_path)
        self._bus.add_signal_receiver(
            response_callback,
            signal_name='Response',
            dbus_interface='org.freedesktop.portal.Request',
            path=request_path
        )

        try:
            options = dbus.Dictionary(args[-1] if args else {}, signature='sv')
            options['handle_token'] = handle_token
            if 'session_handle_token' not in options:
                options['session_handle_token'] = f"sess_{handle_token}"
            new_args = args[:-1] + (options,) if args else (options,)
            logger.debug("Calling portal method with options: %s", dict(options))
            method(*new_args)
            logger.debug("Portal method called, waiting for response...")
            event.wait(timeout=timeout)
            result = result_container[0] if result_container else None
            logger.debug("Portal response: %s", result)
            return result
        finally:
            self._bus.remove_signal_receiver(
                response_callback,
                signal_name='Response',
                dbus_interface='org.freedesktop.portal.Request',
                path=request_path
            )

    def _portal_init(self):
        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self._bus = dbus.SessionBus()

            portal_obj = self._bus.get_object(
                'org.freedesktop.portal.Desktop',
                '/org/freedesktop/portal/desktop'
            )
            self._portal = dbus.Interface(
                portal_obj, 'org.freedesktop.portal.RemoteDesktop'
            )
            self._props = dbus.Interface(
                portal_obj, 'org.freedesktop.DBus.Properties'
            )

            version = self._props.Get(
                'org.freedesktop.portal.RemoteDesktop', 'version'
            )
            logger.info("RemoteDesktop portal version: %d", version)

            self._dbus_loop = GLib.MainLoop()
            t = threading.Thread(target=self._dbus_loop.run, daemon=True)
            t.start()
            time.sleep(0.1)

            # Step 1: CreateSession
            logger.info("Creating portal session...")
            resp = self._portal_call(self._portal.CreateSession, {})
            logger.info("CreateSession response: %s", resp)
            if resp[0] != 0:
                logger.error("Portal CreateSession failed: %s", resp)
                return
            session_handle = ''
            for arg in resp:
                if isinstance(arg, dbus.Dictionary):
                    session_handle = str(arg.get('session_handle', ''))
                    break
            if not session_handle and len(resp) > 1:
                session_handle = str(resp[1].get('session_handle', ''))
            self._session_handle = session_handle
            logger.info("Session handle: %s", self._session_handle)

            # Step 2: SelectDevices (POINTER = 2)
            logger.info("Selecting pointer device...")
            resp = self._portal_call(
                self._portal.SelectDevices,
                dbus.ObjectPath(self._session_handle),
                {'types': dbus.UInt32(2)}
            )
            logger.info("SelectDevices response: %s", resp)

            # Step 3: Start (shows authorization dialog; the user may
            # need a minute to approve, so keep a long timeout here —
            # the automated steps above already use the short default).
            logger.info("Starting session (authorization required)...")
            resp = self._portal_call(
                self._portal.Start,
                dbus.ObjectPath(self._session_handle),
                '',
                {},
                timeout=120
            )
            logger.info("Start response: %s", resp)
            if isinstance(resp, (list, tuple)) and len(resp) > 0:
                if resp[0] == 0:
                    self._portal_ready = True
                    logger.info("Portal session ready!")
                else:
                    logger.error("Portal Start failed: %s", resp)
            else:
                if resp == 0:
                    self._portal_ready = True
                    logger.info("Portal session ready!")
                else:
                    logger.warning("Unexpected Start response format: %s", resp)

        except Exception as exc:
            logger.error("Portal init failed: %s", exc)

    def _warn_once(self, key, msg, *args):
        """WARNING once per reason; repeats at debug so a long macro
        with a dead portal does not flood the log. The first hit also
        goes to warn_fn so the app can show the notice in the UI."""
        warned = self.__dict__.setdefault('_warned', set())
        if key in warned:
            logger.debug(msg, *args)
        else:
            warned.add(key)
            logger.warning(msg, *args)
            if self.warn_fn:
                self.warn_fn(msg % args)

    def _xdotool_pos(self):
        """Read position via xdotool (XWayland-only truth, can be frozen
        on Wayland sessions). Returns (x, y) or None; never raises."""
        try:
            out = subprocess.check_output(
                ['xdotool', 'getmouselocation'],
                stderr=subprocess.DEVNULL, timeout=2
            ).decode().strip()
            parts = dict(p.split(':') for p in out.split() if ':' in p)
            return int(parts['x']), int(parts['y'])
        except Exception as exc:
            logger.debug("xdotool getmouselocation failed: %s", exc)
            return None

    def _kwin_read_setup(self):
        """One-time plumbing for the KWin cursor read. True on success.

        Must run only after _portal_init has started the GLib loop, so
        the probe object's incoming callDBus actually gets dispatched.
        Idempotent and retryable: each stage is guarded so a partial
        failure leaves no half-built state and a later attempt reuses
        what already exists instead of re-registering anything.
        """
        if self._kwin_ready:
            return True
        if self._bus is None or self._dbus_loop is None:
            return False
        # Probe: create once, reuse on later attempts.
        if self._kwin_probe is None:
            # DO_NOT_QUEUE + reply check: if another process owns the
            # name (second instance, stale owner) a plain request_name
            # would silently queue and every read would stall for the
            # full 2 s timeout. Fail fast to the fallback instead.
            try:
                reply = self._bus.request_name(
                    _KWIN_PROBE_NAME,
                    flags=dbus.bus.NAME_FLAG_DO_NOT_QUEUE)
            except Exception as exc:
                logger.debug("KWin probe name request failed: %s", exc)
                return False
            if reply not in (dbus.bus.REQUEST_NAME_REPLY_PRIMARY_OWNER,
                             dbus.bus.REQUEST_NAME_REPLY_ALREADY_OWNER):
                logger.debug(
                    "KWin probe name owned elsewhere (reply %r); "
                    "not queueing.", reply)
                return False
            try:
                self._kwin_probe = _KwinCursorProbe(self._bus)
            except Exception as exc:
                logger.debug("KWin probe setup failed: %s", exc)
                return False
        # Register before the temp stage: a write failure below returns
        # False, so the path recorded there must already have an owner
        # for the case where its own unlink fails.
        if not self._kwin_atexit_registered:
            atexit.register(self._kwin_cleanup)
            self._kwin_atexit_registered = True
        # Temp script: create once; harmless to keep across retries.
        if self._kwin_script_path is None:
            fd = None
            path = None
            try:
                fd, path = tempfile.mkstemp(
                    suffix='.js', prefix='linuxtask_cursor_')
                # Record before writing: the write stage is retried on
                # every read, so a failure here (ENOSPC on tmpfs) must
                # not leave an untracked file behind per attempt.
                self._kwin_script_path = path
                f = os.fdopen(fd, 'w')
                fd = None  # f owns the fd now; the with closes it
                with f:
                    f.write(_KWIN_SCRIPT)
            except Exception as exc:
                logger.debug("KWin script temp file failed: %s", exc)
                if fd is not None:  # fdopen failed: fd never closed
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                if path is not None:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass  # still recorded; atexit retries at exit
                    else:
                        self._kwin_script_path = None
                return False
        try:
            kwin = self._bus.get_object('org.kde.KWin', '/Scripting')
            self._kwin_scripting = dbus.Interface(
                kwin, 'org.kde.kwin.Scripting')
        except Exception as exc:
            logger.debug("KWin Scripting interface failed: %s", exc)
            return False
        self._kwin_ready = True
        return True

    def _kwin_cleanup(self):
        """atexit: remove the script we loaded and the temp file we
        created. Best-effort; deletes nothing we did not create."""
        try:
            if self._kwin_scripting is not None:
                self._kwin_scripting.unloadScript(_KWIN_SCRIPT_NAME)
        except Exception:
            logger.debug("unloadScript at exit failed", exc_info=True)
        try:
            if self._kwin_script_path:
                os.unlink(self._kwin_script_path)
        except OSError:
            pass

    def _kwin_pos_warned(self):
        """_kwin_cursor_pos plus a one-time user-visible warning when it
        fails: a silent fall-through to frozen xdotool would bring the
        original bug back invisibly. Repeats stay DEBUG (_warn_once)."""
        pos = self._kwin_cursor_pos()
        if pos is None:
            self._warn_once(
                "kwin_read",
                "KWin cursor read failed; falling back to xdotool "
                "(may be frozen on Wayland): %s",
                self._kwin_last_error or 'unknown')
        return pos

    def _kwin_cursor_pos(self):
        """Read the true compositor pointer position from KWin's
        scripting API (same mechanism as kdotool). Returns (x, y) or
        None on any failure; never raises. ~6 ms per read.

        Strategy: load the script per read and ALWAYS unload it in the
        finally block, so a read can never leak a KWin script entry and
        two sequential reads can never collide on the script name.
        loadScript uses signature='ss' — the 1-arg overload cannot be
        unloaded by name.
        """
        # Setup rides inside the lock: two concurrent first reads must
        # not race probe registration.
        with self._kwin_lock:
            # Degrade rule: after _KWIN_FAIL_SKIP_AFTER consecutive
            # failures, skip KWin for _KWIN_SKIP_READS reads (one failed
            # probe after the window restarts the window) so a dead KWin
            # cannot stall every read for the full 2 s timeout. A
            # success resets the streak and re-enables KWin at once.
            if (self._kwin_fail_count >= _KWIN_FAIL_SKIP_AFTER
                    and self._kwin_skip_count < _KWIN_SKIP_READS):
                self._kwin_skip_count += 1
                self._kwin_last_error = 'kwin skipped (repeated failures)'
                return None
            # Skip window over (or fresh streak): this is a real
            # attempt, so the next failure restarts the window.
            self._kwin_skip_count = 0
            try:
                if not self._kwin_read_setup():
                    self._kwin_last_error = 'setup failed'
                    self._kwin_fail_count += 1
                    return None
            except Exception:
                self._kwin_last_error = 'setup crashed'
                logger.debug("KWin read setup crashed", exc_info=True)
                self._kwin_fail_count += 1
                return None
            try:
                sid = self._kwin_scripting.loadScript(
                    self._kwin_script_path, _KWIN_SCRIPT_NAME,
                    signature='ss')
                if sid is None or sid < 0:
                    # A stale script with this name (e.g. after a crash)
                    # blocks the load; drop it and retry once.
                    try:
                        self._kwin_scripting.unloadScript(
                            _KWIN_SCRIPT_NAME)
                    except dbus.DBusException:
                        pass
                    sid = self._kwin_scripting.loadScript(
                        self._kwin_script_path, _KWIN_SCRIPT_NAME,
                        signature='ss')
                if sid is None or sid < 0:
                    self._kwin_last_error = 'loadScript failed'
                    self._kwin_fail_count += 1
                    return None
                try:
                    srun = dbus.Interface(
                        self._bus.get_object(
                            'org.kde.KWin', '/Scripting/Script%s' % sid),
                        'org.kde.kwin.Script')
                    self._kwin_probe.reset()
                    srun.run()
                    srun.stop()
                    if not self._kwin_probe.wait(2.0):
                        self._kwin_last_error = 'no reply in 2s'
                        self._kwin_fail_count += 1
                        return None
                    x_s, y_s = self._kwin_probe.payload().split(',')
                    self._kwin_fail_count = 0
                    return int(x_s), int(y_s)
                finally:
                    try:
                        self._kwin_scripting.unloadScript(
                            _KWIN_SCRIPT_NAME)
                    except Exception:
                        logger.debug(
                            "unloadScript failed", exc_info=True)
            except Exception as exc:
                self._kwin_last_error = str(exc) or 'read failed'
                logger.debug("KWin cursor read failed: %s", exc)
                self._kwin_fail_count += 1
                return None

    def get_cursor_pos(self):
        # KWin is the primary source: exact compositor truth. xdotool
        # only works while the pointer is over an XWayland surface and
        # is frozen otherwise.
        pos = self._kwin_pos_warned()
        if pos is not None:
            return pos
        pos = self._xdotool_pos()
        if pos is not None:
            return pos
        # xdotool needs XWayland; without it fall back to our last
        # known position instead of poisoning callers with (0, 0).
        self._lazy_init_tracked_pos()
        return self._cur_x, self._cur_y

    def move_cursor(self, x, y):
        """True when the portal handled the move, False when it was skipped."""
        if not self._portal_ready:
            self._warn_once(
                "move_cursor", "Portal not ready; move to (%d, %d) skipped.",
                x, y)
            return False
        try:
            # Dead reckoning: compute the delta from our own tracked
            # position, NOT from xdotool. XWayland never reports our
            # synthetic moves back, so re-reading it here would compute
            # every delta from a stale origin and the cursor would
            # fight itself (jump forward, snap back). Re-sync happens
            # once per playback in sync_for_playback(), not per move.
            cx, cy = self._clamp(x, y)
            dx = cx - self._cur_x
            dy = cy - self._cur_y
            if dx == 0 and dy == 0:
                return True
            self._portal.NotifyPointerMotion(
                dbus.ObjectPath(self._session_handle), {}, dx, dy
            )
            self._cur_x, self._cur_y = cx, cy
            return True
        except Exception as exc:
            self._warn_once("move_cursor", "Portal move_cursor failed: %s", exc)
            return False

    def _sync_tracked_pos(self):
        """Best-effort refresh of the tracked position from the system."""
        # Same source order as get_cursor_pos: KWin first, xdotool
        # second, tracked fallback last.
        pos = self._kwin_pos_warned()
        if pos is None:
            pos = self._xdotool_pos()
        if pos is not None:
            self._cur_x, self._cur_y = pos
            self._pos_initialized = True
            return
        self._lazy_init_tracked_pos()

    def sync_for_playback(self):
        """One-time position re-sync, called when a replay starts."""
        self._sync_tracked_pos()

    def move_relative(self, dx, dy):
        if not self._portal_ready:
            self._warn_once(
                "move_relative", "Portal not ready; relative move skipped.")
            return False
        try:
            self._lazy_init_tracked_pos()
            self._portal.NotifyPointerMotion(
                dbus.ObjectPath(self._session_handle),
                {}, int(dx), int(dy)
            )
            self._cur_x += int(dx)
            self._cur_y += int(dy)
            return True
        except Exception as exc:
            self._warn_once(
                "move_relative", "Portal move_relative failed: %s", exc)
            return False

    def mouse_button(self, button, pressed):
        if not self._portal_ready:
            self._warn_once(
                "mouse_button", "Portal not ready; button %d skipped.", button)
            return False
        try:
            btn = BTN_MAP.get(button)
            if btn is None:
                self._warn_once(
                    "mouse_button", "No portal mapping for button %d.", button)
                return False
            state = 1 if pressed else 0
            self._portal.NotifyPointerButton(
                dbus.ObjectPath(self._session_handle), {}, btn, state
            )
            return True
        except Exception as exc:
            self._warn_once(
                "mouse_button", "Portal mouse_button failed: %s", exc)
            return False

    def _lazy_init_tracked_pos(self):
        if self._pos_initialized:
            return
        self._pos_initialized = True
        # Inline read (not via get_cursor_pos: that falls back
        # to this method, so calling it here would recurse forever).
        # Source order matches get_cursor_pos: KWin, then xdotool.
        pos = self._kwin_pos_warned()
        if pos is None:
            pos = self._xdotool_pos()
        if pos is not None:
            self._cur_x, self._cur_y = pos
        else:
            logger.debug("no live position available; tracking from (0, 0)",
                         exc_info=True)

    def scroll(self, direction, clicks=1):
        """Performs scroll via portal. Returns True if handled."""
        if not self._portal_ready:
            self._warn_once("scroll", "Portal not ready; scroll skipped.")
            return False
        dy = clicks * 3.0 if direction == 'down' else -clicks * 3.0
        try:
            self._portal.NotifyPointerAxis(
                dbus.ObjectPath(self._session_handle), {}, 0.0, dy
            )
            return True
        except Exception as exc:
            self._warn_once("scroll", "Portal scroll failed: %s", exc)
            return False

    def self_test(self):
        logger.info("--- KDE Wayland Driver Self-Test ---")
        logger.info("Resolution: %dx%d", self.screen_width, self.screen_height)
        logger.info("Portal ready: %s", self._portal_ready)
        pos = self.get_cursor_pos()
        logger.info("Current Position: %s", pos)
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    KdeWaylandDriver().self_test()
