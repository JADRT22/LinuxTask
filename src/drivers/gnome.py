# -*- coding: utf-8 -*-
"""
LinuxTask - gnome.py
Description: GNOME Wayland compositor driver using ydotool.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import subprocess
import shutil
import atexit
import os
import re
import time
import logging
import threading
from evdev.ecodes import BTN_LEFT, BTN_MIDDLE, BTN_RIGHT
from .base import DesktopManager, FALLBACK_RESOLUTION

logger = logging.getLogger(__name__)

# evdev button code -> ydotool button name.
# ydotool: 0x40=LEFT, 0x41=RIGHT, 0x42=MIDDLE.
BTN_MAP = {BTN_LEFT: "0x40", BTN_RIGHT: "0x41", BTN_MIDDLE: "0x42"}

# How long to wait for a freshly spawned ydotoold socket (x 0.1s).
YDOTOOL_SOCKET_RETRIES = 30

# GNOME Shell cursor bridge (extensions/gnome-shell/linuxtask-cursorbridge@jadrt22):
# the extension runs INSIDE the shell and exposes the real pointer via
# D-Bus — global.get_pointer() plus seat.warp_pointer() for absolute
# motion. Wayland compositors do not publish the pointer to clients
# (xdotool only tracks it over XWayland surfaces), so this bridge is the
# primary position source, mirroring the KWin-scripting probe in
# kde_wayland.py.
BRIDGE_NAME = 'org.linuxtask.cursorbridge'
BRIDGE_PATH = '/org/linuxtask/CursorBridge'
BRIDGE_IFACE = 'org.linuxtask.cursorbridge'

# Sync D-Bus timeout for one bridge call (dbus-python seconds / gdbus).
BRIDGE_CALL_TIMEOUT = 0.5

# Degrade after repeated bridge failures: a dead extension or a stopped
# shell must not stall every read for the full timeout. After this many
# consecutive failures the bridge is skipped for BRIDGE_SKIP_READS reads,
# then probed once; a success resets the streak. Same rule as the KWin
# probe (_KWIN_FAIL_SKIP_AFTER / _KWIN_SKIP_READS in kde_wayland.py).
BRIDGE_FAIL_SKIP_AFTER = 3
BRIDGE_SKIP_READS = 8


class GnomeDriver(DesktopManager):
    """Driver for GNOME Wayland using ydotool plus the cursor bridge."""

    def __init__(self):
        super().__init__()
        self.ydotool_path = shutil.which('ydotool')
        self.ydotoold_path = shutil.which('ydotoold')
        self.uid = os.getuid()
        self.socket = f'/run/user/{self.uid}/.ydotool_socket'
        self._tk_instance = None  # Cache for tkinter instance
        atexit.register(self._destroy_tk)

        # --- Cursor bridge plumbing -------------------------------------
        self.warn_fn = None  # main injects it so skipped input becomes a UI notice
        self._warned = set()
        self._bridge_lock = threading.Lock()
        self._bridge_mode = None   # 'dbus' (importable bindings) or 'gdbus'
        self._bridge_ready = False
        self._bridge_bus = None    # dbus-python SessionBus (dbus mode)
        self._bridge_proxy = None  # cached proxy object (dbus mode)
        self._bridge_fail_count = 0
        self._bridge_skip_count = 0
        self._bridge_warp_fail_count = 0
        self._bridge_setup()      # before resolution: GetScreenSize is exact
        self._detect_resolution()
        self.supports_absolute_positioning = self._bridge_ready
        self.ensure_daemon()

    def _destroy_tk(self):
        """Destroys the cached tkinter instance, if any."""
        try:
            if self._tk_instance is not None:
                self._tk_instance.destroy()
                self._tk_instance = None
        except Exception:
            logger.debug("Failed to destroy tkinter instance.", exc_info=True)

    # ------------------------------------------------------------------
    # GNOME Shell cursor bridge
    # ------------------------------------------------------------------

    def _warn_once(self, key, msg, *args):
        """Logs the message at WARNING once per session; repeats stay DEBUG.

        Mirrors kde_wayland._warn_once. When main has injected warn_fn,
        the first occurrence also becomes a one-time UI notice.
        """
        if key in self._warned:
            logger.debug(msg + " (repeated)", *args)
            return
        self._warned.add(key)
        logger.warning(msg, *args)
        if self.warn_fn:
            try:
                self.warn_fn(msg % args)
            except Exception:
                logger.debug("warn_fn suppressed: %s", msg, exc_info=True)

    def _bridge_setup(self):
        """Probes the cursor bridge and picks the calling mode.

        dbus-python (python3-dbus) is preferred when importable: reads
        then happen in-process. Otherwise each call goes through a
        short-lived `gdbus` subprocess. Neither is required — without
        both, self._bridge_ready stays False and the driver keeps its
        legacy relative-delta behavior.
        """
        self._bridge_gdbus = shutil.which('gdbus')

        bus = None
        try:
            import dbus
            bus = dbus.SessionBus()
        except Exception as exc:
            logger.debug("python-dbus unavailable for the cursor bridge: %s", exc)

        if bus is not None:
            try:
                if bus.name_has_owner(BRIDGE_NAME):
                    self._bridge_bus = bus
                    self._bridge_mode = 'dbus'
                    self._bridge_ready = True
                    logger.info("GNOME cursor bridge detected (dbus mode).")
                    return
            except Exception as exc:
                logger.debug("bridge name check failed: %s", exc)

        if self._bridge_gdbus:
            try:
                out = subprocess.check_output(
                    ['gdbus', 'call', '--session',
                     '--dest', 'org.freedesktop.DBus',
                     '--object-path', '/org/freedesktop/DBus',
                     '--method', 'org.freedesktop.DBus.NameHasOwner',
                     BRIDGE_NAME],
                    timeout=2
                ).decode()
                if '"true"' in out:
                    self._bridge_mode = 'gdbus'
                    self._bridge_ready = True
                    logger.info("GNOME cursor bridge detected (gdbus mode).")
            except (subprocess.CalledProcessError, FileNotFoundError,
                    subprocess.TimeoutExpired, UnicodeDecodeError) as exc:
                logger.debug("bridge gdbus probe failed: %s", exc)

        if not self._bridge_ready:
            logger.info(
                "GNOME cursor bridge not found (extension not installed "
                "or disabled). Absolute positioning falls back to "
                "relative deltas; install the extension via "
                "tools/install-gnome-bridge.sh."
            )

    def _bridge_proxy_get(self):
        """Lazily builds (and caches) the dbus-mode proxy object."""
        if self._bridge_proxy is None:
            proxy = self._bridge_bus.get_object(BRIDGE_NAME, BRIDGE_PATH)
            self._bridge_proxy = proxy
        return self._bridge_proxy

    def _bridge_invalidate(self):
        """Forgets the cached proxy so the next dbus call rebuilds it."""
        self._bridge_proxy = None

    def _bridge_call(self, method, args, timeout):
        """Calls one bridge method.

        Returns the parsed python values (list) on success, None on any
        failure. Thread-safe: recorder and playback threads may both
        reach the bridge, and dbus-mode connections are not guaranteed
        to be reentrant.
        """
        with self._bridge_lock:
            if self._bridge_mode == 'dbus':
                try:
                    import dbus
                    proxy = self._bridge_proxy_get()
                    reply = proxy.get_dbus_method(method, BRIDGE_IFACE)(
                        *args, timeout=BRIDGE_CALL_TIMEOUT)
                    return list(reply)
                except Exception as exc:
                    self._bridge_invalidate()
                    logger.debug("bridge %s (dbus) failed: %s", method, exc)
                    return None
            if self._bridge_mode == 'gdbus':
                try:
                    cmdline = ['gdbus', 'call', '--session',
                               '--dest', BRIDGE_NAME,
                               '--object-path', BRIDGE_PATH,
                               '--method', f'{BRIDGE_IFACE}.{method}']
                    arg_list = list(args)
                    timeout_s = timeout
                    if arg_list:
                        cmdline += [str(a) for a in arg_list]
                    out = subprocess.check_output(
                        cmdline, timeout=timeout_s).decode()
                    return self._gdbus_parse(out)
                except (subprocess.CalledProcessError, FileNotFoundError,
                        subprocess.TimeoutExpired, UnicodeDecodeError) as exc:
                    logger.debug("bridge %s (gdbus) failed: %s", method, exc)
                    return None
            return None

    @staticmethod
    def _gdbus_parse(output):
        """Parses gdbus output like `(-1, 340)` into a python list."""
        m = re.fullmatch(r'\(\s*([^\)]*)\s*\)', output.strip())

        def _loose(x):
            try:
                return float(x) if ('.' in x) else int(x)
            except (ValueError, TypeError):
                return 0

        if m:
            values = [_loose(v.strip().strip("',\""))
                      for v in m.group(1).split(',') if v.strip()]
            # "()"/junk that parsed into nothing is not a valid reply.
            return values if values else None

        return None

    # -- Reads (position) --------------------------------------------------

    def _bridge_read_pos(self):
        """One bridge read with the degrade rule. Returns (x, y) or None."""
        with self._bridge_lock:
            if self._bridge_skip_count > 0:
                self._bridge_skip_count -= 1
                return None

        pos = self._bridge_call('GetPointer', (), BRIDGE_CALL_TIMEOUT)
        if pos is None or len(pos) < 2:
            with self._bridge_lock:
                self._bridge_fail_count += 1
                if self._bridge_fail_count >= BRIDGE_FAIL_SKIP_AFTER:
                    self._bridge_fail_count = 0
                    self._bridge_skip_count = BRIDGE_SKIP_READS
                    self._warn_once(
                        'bridge_degrade',
                        "GNOME cursor bridge read failed %d times in a row; "
                        "skipping it for a few reads (falls back to "
                        "xdotool/tkinter, stale over pure Wayland surfaces).",
                        BRIDGE_FAIL_SKIP_AFTER)
            return None

        with self._bridge_lock:
            self._bridge_fail_count = 0
        try:
            return int(pos[0]), int(pos[1])
        except (TypeError, ValueError, IndexError):
            return None

    def get_cursor_pos(self):
        """Returns cursor position: bridge first, then xdotool, then tkinter."""
        if self._bridge_ready:
            pos = self._bridge_read_pos()
            if pos is not None:
                return pos
            # Bridge answered with junk / degrade rule active — fall
            # through to the legacy chain below.
        return self._legacy_get_cursor_pos()

    def _legacy_get_cursor_pos(self):
        """Pre-bridge chain: xdotool, then tkinter. Stale over pure
        Wayland surfaces (XWayland only sees what it hosts)."""
        if shutil.which('xdotool'):
            try:
                out = subprocess.check_output(
                    ['xdotool', 'getmouselocation'], stderr=subprocess.DEVNULL
                ).decode().strip()
                parts = dict(p.split(':') for p in out.split() if ':' in p)
                return int(parts['x']), int(parts['y'])
            except Exception as exc:
                logger.debug("get_cursor_pos (xdotool) failed: %s", exc)
        try:
            import tkinter as tk
            if self._tk_instance is None:
                self._tk_instance = tk.Tk()
                self._tk_instance.withdraw()  # Hide the window
            # Update must be called to get fresh coordinates in some environments
            self._tk_instance.update()
            x, y = self._tk_instance.winfo_pointerx(), self._tk_instance.winfo_pointery()
            return x, y
        except Exception as exc:
            logger.debug("get_cursor_pos (tkinter) failed: %s", exc)

        return None

    # -- Writes (absolute move) -------------------------------------------

    def _bridge_warp(self, x, y):
        """Warps the cursor through the bridge. True on success."""
        if not self._bridge_ready:
            return False
        reply = self._bridge_call('WarpPoint', (int(x), int(y)),
                                  BRIDGE_CALL_TIMEOUT)
        if reply is None:
            self._bridge_warp_fail_count += 1
            if self._bridge_warp_fail_count >= BRIDGE_FAIL_SKIP_AFTER:
                # Stop hammering a dead bridge: disable absolute moves for
                # this session so move_cursor hands over to relative
                # emulation instead of paying the timeout every event.
                self._bridge_ready = False
                self.supports_absolute_positioning = False
                self._warn_once(
                    'warp_degrade',
                    "GNOME cursor bridge WarpPoint failed %d times in a "
                    "row; absolute moves disabled for this session "
                    "(falling back to relative deltas).",
                    BRIDGE_FAIL_SKIP_AFTER)
            return False
        self._bridge_warp_fail_count = 0
        return True

    def move_cursor(self, x, y):
        """Moves the cursor to absolute (x, y).

        With the bridge installed this is a real absolute jump
        (seat.warp_pointer). Without it, GNOME has no absolute cursor
        API for clients, so the legacy path emulates absolute via a
        relative delta computed from the current position.
        """
        try:
            x, y = self._clamp(x, y)
            if self._bridge_ready and self._bridge_warp(x, y):
                return
            if not self._bridge_ready:
                self._warn_once(
                    'abs_fallback',
                    "Absolute move emulated by relative delta (no cursor "
                    "bridge); recording/replay may drift. Install "
                    "tools/install-gnome-bridge.sh's extension for real "
                    "absolute positioning.")
            pos = self.get_cursor_pos()
            if pos is None:
                logger.error("move_cursor aborted: cursor pos unknown")
                return
            cur_x, cur_y = pos
            self.move_relative(int(x) - int(cur_x), int(y) - int(cur_y))
        except Exception as exc:
            logger.error("move_cursor(%s, %s) failed: %s", x, y, exc)

    def move_relative(self, dx, dy):
        """Moves cursor by relative offset using ydotool."""
        if not self.ydotool_path:
            return False
        try:
            env = os.environ.copy()
            env['YDOTOOL_SOCKET'] = self.socket
            subprocess.run(
                [self.ydotool_path, 'mousemove', '--',
                 str(int(dx)), str(int(dy))],
                env=env, capture_output=True, check=True
            )
            return True
        except subprocess.CalledProcessError as exc:
            logger.error("ydotool move_relative failed: %s", exc)
            self.ensure_daemon()
            return False
        except FileNotFoundError:
            logger.error("ydotool binary not found.")
            return False

    def mouse_button(self, button, pressed):
        """Handles mouse button via ydotool mousedown/mouseup."""
        ydo_btn = BTN_MAP.get(button)

        if not ydo_btn or not self.ydotool_path:
            return False

        action = 'mousedown' if pressed else 'mouseup'
        try:
            env = os.environ.copy()
            env['YDOTOOL_SOCKET'] = self.socket
            subprocess.run(
                [self.ydotool_path, action, ydo_btn],
                env=env, capture_output=True, check=True
            )
            return True
        except subprocess.CalledProcessError as exc:
            logger.error("ydotool %s failed: %s", action, exc)
            return False

    def scroll(self, direction, clicks=1):
        """Performs scroll via ydotool. Returns True if handled."""
        if not self.ydotool_path:
            return False
        try:
            env = os.environ.copy()
            env['YDOTOOL_SOCKET'] = self.socket
            # ydotool mousemove uses --wheel for scroll
            value = clicks if direction == 'up' else -clicks
            subprocess.run(
                [self.ydotool_path, 'mousemove', '--wheel', '--',
                 '0', str(value)],
                env=env, capture_output=True, check=True
            )
            return True
        except subprocess.CalledProcessError as exc:
            logger.error("ydotool scroll failed: %s", exc)
            return False

    def ensure_daemon(self):
        """Ensures ydotoold is running with our socket.

        Only kills our own socket's daemon, not all ydotoold processes.
        """
        if not self.ydotoold_path:
            logger.warning("ydotoold not found. Mouse movement will not work.")
            return
        if not self.ydotool_path:
            logger.warning("ydotool not found. Mouse movement will not work.")
            return

        # Check if socket already exists and is functional
        if os.path.exists(self.socket):
            try:
                env = os.environ.copy()
                env['YDOTOOL_SOCKET'] = self.socket
                result = subprocess.run(
                    [self.ydotool_path, 'mousemove', '--', '0', '0'],
                    env=env, capture_output=True, timeout=2
                )
                if result.returncode == 0:
                    logger.info("Existing ydotoold socket is functional.")
                    return
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        # Socket is stale or missing — clean up and restart
        try:
            if os.path.exists(self.socket) and not os.path.islink(self.socket):
                os.unlink(self.socket)
        except OSError as exc:
            logger.warning("Could not remove stale socket: %s", exc)

        try:
            subprocess.Popen(
                [self.ydotoold_path, '--socket-path', self.socket],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            for _ in range(YDOTOOL_SOCKET_RETRIES):
                if os.path.exists(self.socket):
                    # 0o600: only the owner can inject input through this socket.
                    os.chmod(self.socket, 0o600)
                    logger.info("ydotoold started with socket: %s", self.socket)
                    return
                time.sleep(0.1)
            logger.error("ydotoold started but socket never appeared.")
        except FileNotFoundError:
            logger.error("ydotoold binary not found.")
        except OSError as exc:
            logger.error("Failed to start ydotoold: %s", exc)

    def _detect_resolution(self):
        """Dynamic resolution detection for GNOME/Wayland."""
        # Prefer the bridge: GetScreenSize reports the shell's logical
        # stage size directly — exact, and independent of XWayland.
        if self._bridge_ready:
            size = self._bridge_call('GetScreenSize', (), BRIDGE_CALL_TIMEOUT)
            if size is not None and len(size) >= 2:
                try:
                    self.screen_width, self.screen_height = int(size[0]), int(size[1])
                    if self.screen_width > 0 and self.screen_height > 0:
                        return
                except (TypeError, ValueError, IndexError):
                    pass
            self._warn_once(
                'bridge_resolution',
                "Bridge present but GetScreenSize failed; using "
                "xrandr/mutter for resolution.")

        # Try xrandr next (covers XWayland scenarios)
        try:
            out = subprocess.check_output(
                ['xrandr'], stderr=subprocess.STDOUT, timeout=5
            ).decode()
            for line in out.splitlines():
                if '*' in line:
                    match = re.search(r'(\d+)x(\d+)', line)
                    if match:
                        self.screen_width = int(match.group(1))
                        self.screen_height = int(match.group(2))
                        return
        except (subprocess.CalledProcessError, FileNotFoundError,
                subprocess.TimeoutExpired) as exc:
            logger.debug("xrandr failed: %s", exc)

        # Fallback: Query org.gnome.Mutter.DisplayConfig via gdbus
        try:
            cmd = [
                'gdbus', 'call', '--session', '--dest',
                'org.gnome.Mutter.DisplayConfig',
                '--object-path', '/org/gnome/Mutter/DisplayConfig',
                '--method', 'org.gnome.Mutter.DisplayConfig.GetCurrentState'
            ]
            out = subprocess.check_output(cmd, timeout=5).decode()
            if "'is-current': <true>" in out:
                pattern = (
                    r"'\d+x\d+@[\d\.]+',\s+(\d+),\s+(\d+).*?"
                    r"'is-current':\s+<true>"
                )
                match = re.search(pattern, out, re.DOTALL)
                if match:
                    self.screen_width = int(match.group(1))
                    self.screen_height = int(match.group(2))
                    return
        except (subprocess.CalledProcessError, FileNotFoundError,
                subprocess.TimeoutExpired) as exc:
            logger.debug("gdbus resolution detection failed: %s", exc)

        self.screen_width, self.screen_height = FALLBACK_RESOLUTION
        logger.warning("Using fallback resolution: 1920x1080")
