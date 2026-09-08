import subprocess
import time
import logging
import dbus
import dbus.mainloop.glib
from gi.repository import GLib
import threading
import queue
import re

from .base import DesktopManager

logger = logging.getLogger(__name__)


class KdeWaylandDriver(DesktopManager):
    """KDE Wayland driver using Portal RemoteDesktop for cursor control."""

    def __init__(self):
        super().__init__()
        self._session_handle = None
        self._cur_x = 0
        self._cur_y = 0
        self._pos_initialized = False
        self._portal_ready = False
        self._response_queue = queue.Queue()
        self._dbus_loop = None
        self._bus = None
        self._screen_width = 0
        self._screen_height = 0
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
                    self._screen_width = int(m.group(1))
                    self._screen_height = int(m.group(2))
                    logger.info(
                        "Resolution (kscreen): %dx%d",
                        self._screen_width, self._screen_height)
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
                        self._screen_width = int(m.group(1))
                        self._screen_height = int(m.group(2))
                        logger.info("Resolution: %dx%d",
                                    self._screen_width, self._screen_height)
                        return
        except Exception:
            pass
        self._screen_width, self._screen_height = 1920, 1080
        logger.warning("Using fallback resolution: 1920x1080")

    def _predict_request_path(self, token):
        name = self._bus.get_unique_name().replace('.', '_').replace(':', '')
        return f"/org/freedesktop/portal/desktop/request/{name}/{token}"

    def _portal_call(self, method, *args, timeout=120):
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

            # Step 3: Start (shows authorization dialog)
            logger.info("Starting session (authorization required)...")
            resp = self._portal_call(
                self._portal.Start,
                dbus.ObjectPath(self._session_handle),
                '',
                {}
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

    def get_cursor_pos(self):
        try:
            out = subprocess.check_output(
                ['xdotool', 'getmouselocation'],
                stderr=subprocess.DEVNULL, timeout=2
            ).decode().strip()
            parts = dict(p.split(':') for p in out.split() if ':' in p)
            return int(parts['x']), int(parts['y'])
        except Exception as exc:
            logger.debug("xdotool getmouselocation failed: %s", exc)
        # xdotool needs XWayland; without it fall back to our last
        # known position instead of poisoning callers with (0, 0).
        self._lazy_init_tracked_pos()
        return self._cur_x, self._cur_y

    def _clamp(self, x, y):
        return (
            max(0, min(int(x), self._screen_width - 1)),
            max(0, min(int(y), self._screen_height - 1))
        )

    def move_cursor(self, x, y):
        if not self._portal_ready:
            return
        try:
            # Re-sync with the real cursor before computing the delta:
            # the user may have moved the physical mouse since our last
            # tracked move, and the portal only accepts relative motion.
            self._sync_tracked_pos()
            cx, cy = self._clamp(x, y)
            dx = cx - self._cur_x
            dy = cy - self._cur_y
            if dx == 0 and dy == 0:
                return
            self._portal.NotifyPointerMotion(
                dbus.ObjectPath(self._session_handle), {}, dx, dy
            )
            self._cur_x, self._cur_y = cx, cy
        except Exception as exc:
            logger.error("Portal move_cursor failed: %s", exc)

    def _sync_tracked_pos(self):
        """Best-effort refresh of the tracked position from the system."""
        try:
            out = subprocess.check_output(
                ['xdotool', 'getmouselocation'],
                stderr=subprocess.DEVNULL, timeout=2
            ).decode().strip()
            parts = dict(p.split(':') for p in out.split() if ':' in p)
            self._cur_x, self._cur_y = int(parts['x']), int(parts['y'])
            self._pos_initialized = True
        except Exception as exc:
            logger.debug("tracked-pos sync failed: %s", exc)
            self._lazy_init_tracked_pos()

    def move_relative(self, dx, dy):
        if not self._portal_ready:
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
            logger.error("Portal move_relative failed: %s", exc)
            return False

    def mouse_button(self, button, pressed):
        if not self._portal_ready:
            return False
        try:
            btn_map = {272: 1, 273: 3, 274: 2}
            btn = btn_map.get(button)
            if btn is None:
                return False
            state = 1 if pressed else 0
            self._portal.NotifyPointerButton(
                dbus.ObjectPath(self._session_handle), {}, btn, state
            )
            return True
        except Exception as exc:
            logger.error("Portal mouse_button failed: %s", exc)
            return False

    def _lazy_init_tracked_pos(self):
        if self._pos_initialized:
            return
        self._pos_initialized = True
        # Inline xdotool read (not via get_cursor_pos: that falls back
        # to this method, so calling it here would recurse forever).
        try:
            out = subprocess.check_output(
                ['xdotool', 'getmouselocation'],
                stderr=subprocess.DEVNULL, timeout=2
            ).decode().strip()
            parts = dict(p.split(':') for p in out.split() if ':' in p)
            self._cur_x, self._cur_y = int(parts['x']), int(parts['y'])
        except Exception:
            logger.debug("no live position available; tracking from (0, 0)")

    def scroll(self, direction, clicks=1):
        """Performs scroll via portal. Returns True if handled."""
        if not self._portal_ready:
            return False
        dy = clicks * 3.0 if direction == 'down' else -clicks * 3.0
        try:
            self._portal.NotifyPointerAxis(
                dbus.ObjectPath(self._session_handle), {}, 0.0, dy
            )
            return True
        except Exception as exc:
            logger.debug("Portal scroll failed: %s", exc)
            return False

    def self_test(self):
        print("--- KDE Wayland Driver Self-Test ---")
        print(f"Resolution: {self._screen_width}x{self._screen_height}")
        print(f"Portal ready: {self._portal_ready}")
        pos = self.get_cursor_pos()
        print(f"Current Position: {pos}")
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    KdeWaylandDriver().self_test()
