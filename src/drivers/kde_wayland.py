# -*- coding: utf-8 -*-
"""
LinuxTask - kde_wayland.py
Description: KDE Wayland driver using the xdg-desktop-portal
             RemoteDesktop interface, with a KWin scripting probe for
             reading the real pointer position.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import atexit
import json
import logging
import os
import re
import secrets
import subprocess
import tempfile
import threading
import time

import dbus
import dbus.mainloop.glib
import dbus.service
from evdev.ecodes import BTN_LEFT, BTN_MIDDLE, BTN_RIGHT
from gi.repository import GLib

from .base import FALLBACK_RESOLUTION, DesktopManager

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


def _kwin_script(nonce):
    """Source of the one-shot KWin script reporting workspace.cursorPos.

    The nonce comes back as the first field of the payload, so a reply that
    belongs to an earlier (timed-out) read can be told apart from the reply
    this read is waiting for. kdotool uses the same callDBus mechanism.
    """
    return (
        'callDBus("%s", "/", "%s", "result", "%d," + workspace.cursorPos.x '
        '+ "," + workspace.cursorPos.y);\n'
        % (_KWIN_PROBE_NAME, _KWIN_PROBE_NAME, nonce)
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

    Two filters protect the value that playback's dead reckoning is built
    on top of:

    * sender — only the process that currently owns org.kde.KWin is
      believed. The session bus is shared with every app the user runs, so
      without this any of them could claim a cursor position of its choice
      and steer the replayed clicks somewhere else.
    * nonce — a reply from a read that already timed out is dropped instead
      of being mistaken for the current read's answer.

    With no trusted sender configured yet (name lookup failed) the filter
    stays open: refusing every reply would turn a hard-to-reach KWin into a
    dead read path.
    """

    def __init__(self, bus):
        self._event = threading.Event()
        self._value = None
        self._nonce = None
        self.expected_senders = set()
        self.saw_rejection = False
        self.rejected = 0
        super().__init__(conn=bus, object_path='/')

    def trust_sender(self, unique_name):
        """Records a bus name whose replies are accepted (org.kde.KWin's)."""
        if unique_name:
            self.expected_senders.add(str(unique_name))

    @dbus.service.method(_KWIN_PROBE_NAME, in_signature='s',
                         out_signature='', sender_keyword='sender')
    def result(self, payload, sender=None):
        if self.expected_senders and sender not in self.expected_senders:
            self.rejected += 1
            # Read by the driver outside this handler, where a blocking
            # name lookup is allowed: KWin restarting gives this service a
            # new unique name, and the stale one must be re-resolved.
            self.saw_rejection = True
            logger.warning(
                "Ignoring cursor position reply from %s (not KWin).", sender)
            return
        fields = str(payload).split(',', 1)
        if self._nonce is not None:
            if len(fields) < 2 or fields[0] != self._nonce:
                self.rejected += 1
                logger.debug(
                    "Ignoring stale cursor reply (nonce %s, expected %s).",
                    fields[0] if fields else '', self._nonce)
                return
            self._value = fields[1]
        else:
            self._value = str(payload)
        self._event.set()

    def reset(self, nonce=None):
        self._nonce = None if nonce is None else str(nonce)
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
        # Cached unique name of org.freedesktop.portal.Desktop, used to
        # verify who emitted a Response signal (see _portal_call).
        self._portal_sender = None
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
        """Detects the primary size and the whole layout box.

        kscreen-doctor --json is the precise source (positions, modes,
        enabled state) and gives every output, so the clamp box becomes the
        union of the layout instead of the first output in the list. The
        text listing and xrandr stay as fallbacks for older Plasma and for
        XWayland sessions.
        """
        if self._detect_resolution_kscreen_json():
            return
        if self._detect_resolution_kscreen_text():
            return
        if self._detect_resolution_xrandr():
            return
        self.set_screen_size(*FALLBACK_RESOLUTION)
        logger.warning("Using fallback resolution: 1920x1080")

    @staticmethod
    def _output_geometry(entry):
        """Extracts (x, y, w, h, enabled, primary) from one kscreen entry.

        The JSON shape has moved between Plasma releases (a bare list, a
        wrapper object, and each output's fields living under 'output'), so
        only the fields we need are read, defensively. Rotation is ignored:
        kscreen reports the mode size, and a rotated output would then have
        its width and height swapped — a wrong-but-inside-the-box estimate
        is better than refusing the whole layout.
        """
        if not isinstance(entry, dict):
            return None
        data = entry.get('output') if isinstance(
            entry.get('output'), dict) else entry
        mode = data.get('mode') or data.get('currentMode') or {}
        if isinstance(mode, dict):
            size = mode.get('size') if isinstance(
                mode.get('size'), dict) else mode
        else:
            return None
        pos = data.get('pos') or data.get('position') or {}
        try:
            width = int(size.get('width', 0) or 0)
            height = int(size.get('height', 0) or 0)
        except (TypeError, ValueError):
            return None
        if width <= 0 or height <= 0:
            return None
        try:
            x = int(pos.get('x', 0) or 0)
            y = int(pos.get('y', 0) or 0)
        except (TypeError, ValueError):
            x = y = 0
        return (
            x, y, width, height,
            bool(data.get('enabled', True)),
            bool(data.get('primary'))
        )

    def _apply_outputs(self, geometries, source):
        """Records the primary size and the union box of `geometries`."""
        active = [g for g in geometries if g[4]]
        if not active:
            return False
        primary = next((g for g in active if g[5]),
                       next((g for g in active
                             if g[0] == 0 and g[1] == 0), active[0]))
        bounds = (
            min(g[0] for g in active), min(g[1] for g in active),
            max(g[0] + g[2] for g in active),
            max(g[1] + g[3] for g in active)
        )
        self.set_screen_size(primary[2], primary[3], bounds)
        logger.info(
            "Resolution (%s): %dx%d, layout %dx%d%+d%+d",
            source, primary[2], primary[3],
            bounds[2] - bounds[0], bounds[3] - bounds[1],
            bounds[0], bounds[1]
        )
        return True

    def _detect_resolution_kscreen_json(self):
        """Parses `kscreen-doctor --json`. True when it produced geometry."""
        try:
            out = subprocess.check_output(
                ['kscreen-doctor', '--json'],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode()
            payload = json.loads(out)
        except Exception as exc:
            logger.debug("kscreen-doctor --json failed: %s", exc)
            return False
        if isinstance(payload, dict):
            entries = payload.get('outputs')
            if entries is None:
                entries = [payload]
        elif isinstance(payload, list):
            entries = payload
        else:
            return False
        if not isinstance(entries, list):
            return False
        geometries = [
            g for g in (self._output_geometry(e) for e in entries) if g
        ]
        return self._apply_outputs(geometries, 'kscreen-json')

    def _detect_resolution_kscreen_text(self):
        """Parses the human `kscreen-doctor -o` listing for one output.

        Only the active mode of each output line is read, and no position
        information is available here, so the layout box cannot be
        reconstructed: this path keeps the historical primary-only
        behaviour. kscreen marks the active mode with '*' and uses ANSI
        colors, so strip escapes first.
        """
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
                    self.set_screen_size(int(m.group(1)), int(m.group(2)))
                    logger.info(
                        "Resolution (kscreen): %dx%d",
                        self.screen_width, self.screen_height)
                    return True
        except Exception as exc:
            logger.debug("kscreen-doctor failed: %s", exc)
        return False

    def _detect_resolution_xrandr(self):
        """Falls back to xrandr, which does report output offsets.

        xrandr only mirrors XWayland, so on a Wayland session this can be
        wrong or empty; it is used only when kscreen gave nothing.
        """
        try:
            out = subprocess.check_output(
                ['xrandr'], stderr=subprocess.DEVNULL, timeout=2
            ).decode()
        except Exception:
            logger.debug("xrandr fallback failed.", exc_info=True)
            return False
        active = []
        primary_seen = False
        for line in out.splitlines():
            if ' connected' not in line:
                continue
            is_primary = ' primary' in line
            # '2560x1440+1920+0' carries both the size and the layout
            # offset; the mode line below the connector repeats the size
            # with a '*', but without an offset. xrandr writes the offset
            # sign itself, so a negative Y reads '+2560-180' — matching
            # only '+', as a naive pattern does, silently drops every
            # monitor that sits above the primary one.
            m = re.search(r'(\d+)x(\d+)([+-]\d+)([+-]\d+)', line)
            if not m:
                continue
            x, y = int(m.group(3)), int(m.group(4))
            width, height = int(m.group(1)), int(m.group(2))
            active.append(
                (x, y, width, height, True, is_primary or not primary_seen)
            )
            primary_seen = primary_seen or is_primary
        if not active:
            for line in out.splitlines():
                if '*' in line:
                    m = re.search(r'(\d+)x(\d+)', line)
                    if m:
                        self.set_screen_size(
                            int(m.group(1)), int(m.group(2)))
                        logger.info("Resolution: %dx%d",
                                    self.screen_width, self.screen_height)
                        return True
            return False
        return self._apply_outputs(active, 'xrandr')

    def _predict_request_path(self, token):
        name = self._bus.get_unique_name().replace('.', '_').replace(':', '')
        return f"/org/freedesktop/portal/desktop/request/{name}/{token}"

    def _portal_owner(self):
        """Unique bus name of the portal, cached; None when unknown.

        Used to check who really emitted a Response signal. Re-resolved
        after a rejected signal, because a portal restart changes the name.
        """
        if self._portal_sender is not None:
            return self._portal_sender
        try:
            self._portal_sender = str(self._bus.get_name_owner(
                'org.freedesktop.portal.Desktop'))
        except Exception as exc:
            logger.debug("Could not resolve the portal owner: %s", exc)
            self._portal_sender = None
        return self._portal_sender

    def _portal_call(self, method, *args, timeout=15):
        # Random, not time-derived: the request path is predictable from the
        # token, and a predictable path plus an unfiltered match rule would
        # let any process on the session bus answer a portal request.
        handle_token = 'ht_%s' % secrets.token_hex(8)
        request_path = self._predict_request_path(handle_token)
        event = threading.Event()
        result_container = []
        expected_sender = self._portal_owner()

        def response_callback(*resp_args, sender=None):
            if expected_sender and sender != expected_sender:
                logger.warning(
                    "Ignoring portal Response from %s on %s.", sender,
                    request_path)
                # Drop the cached owner so the next call re-resolves it.
                self._portal_sender = None
                return
            logger.debug("Portal response signal: %s", resp_args)
            result_container.append(resp_args)
            event.set()

        logger.debug("Subscribing to portal response on: %s", request_path)
        self._bus.add_signal_receiver(
            response_callback,
            signal_name='Response',
            dbus_interface='org.freedesktop.portal.Request',
            path=request_path,
            sender_keyword='sender'
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
                    # Placeholder: every read rewrites this file with its
                    # own nonce (see _kwin_write_script).
                    f.write(_kwin_script(0))
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
        # Trust only KWin's replies, resolved here (outside the probe's own
        # handler, where a blocking name lookup would re-enter the
        # connection).
        self._kwin_trust_kwin()
        self._kwin_ready = True
        return True

    def _kwin_trust_kwin(self):
        """Points the probe at the current unique name of org.kde.KWin."""
        if self._kwin_probe is None or self._bus is None:
            return
        try:
            owner = str(self._bus.get_name_owner('org.kde.KWin'))
        except Exception as exc:
            logger.debug("Could not resolve org.kde.KWin owner: %s", exc)
            return
        if owner:
            self._kwin_probe.trust_sender(owner)

    def _kwin_write_script(self, nonce):
        """Writes this read's script (with its nonce) to the temp file.

        True on success. The file is ours alone (mkstemp, 0600) and is
        reloaded by KWin on every loadScript, so a per-read rewrite is the
        cheapest way to tag replies.
        """
        if not self._kwin_script_path:
            return False
        try:
            with open(self._kwin_script_path, 'w',
                      encoding='utf-8') as script_file:
                script_file.write(_kwin_script(nonce))
            return True
        except OSError as exc:
            logger.debug("KWin script rewrite failed: %s", exc)
            return False

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
                # A rejected reply means the KWin unique name the probe
                # trusts is stale (KWin restarted): re-resolve it, then let
                # this read tag its own nonce into the script.
                if getattr(self._kwin_probe, 'saw_rejection', False) is True:
                    self._kwin_trust_kwin()
                    self._kwin_probe.saw_rejection = False
                nonce = time.time_ns() % 1000000000
                if not self._kwin_write_script(nonce):
                    self._kwin_last_error = 'script write failed'
                    self._kwin_fail_count += 1
                    return None
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
                    self._kwin_probe.reset(nonce)
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
        if pos is None:
            pos = self._xdotool_pos()
        if pos is not None:
            # A live read is also the dead-reckoning origin: move_cursor
            # computes its delta from _cur, so leaving it stale here
            # makes every absolute move land at the wrong place (from
            # (0, 0) on a fresh driver, or from wherever the last
            # playback happened to be).
            self._cur_x, self._cur_y = pos
            self._pos_initialized = True
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
            #
            # The origin must be anchored first, though: a driver whose
            # tracked position was never initialised computes the first
            # delta from (0, 0), so the pointer ends up at
            # (real + target) instead of at target. One live read fixes
            # it, and only costs anything while the position is cold.
            if not self._pos_initialized:
                self._lazy_init_tracked_pos()
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
        # Inline read (not via get_cursor_pos: that falls back
        # to this method, so calling it here would recurse forever).
        # Source order matches get_cursor_pos: KWin, then xdotool.
        pos = self._kwin_pos_warned()
        if pos is None:
            pos = self._xdotool_pos()
        # Mark the position as initialised only on a successful read:
        # a failed one must leave it cold so the next move_cursor tries
        # to anchor again instead of dead-reckoning from (0, 0) forever.
        if pos is not None:
            self._cur_x, self._cur_y = pos
            self._pos_initialized = True
        else:
            # No exception is active here, so no exc_info: this is the
            # expected shape of a read that simply has no source available.
            logger.debug(
                "No live position available; staying cold so the next "
                "move_cursor anchors instead of dead-reckoning from (0, 0)."
            )

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
