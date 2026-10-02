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
from evdev.ecodes import BTN_LEFT, BTN_MIDDLE, BTN_RIGHT
from .base import DesktopManager, FALLBACK_RESOLUTION

logger = logging.getLogger(__name__)

# evdev button code -> ydotool button name.
# ydotool: 0x40=LEFT, 0x41=RIGHT, 0x42=MIDDLE.
BTN_MAP = {BTN_LEFT: "0x40", BTN_RIGHT: "0x41", BTN_MIDDLE: "0x42"}

# How long to wait for a freshly spawned ydotoold socket (x 0.1s).
YDOTOOL_SOCKET_RETRIES = 30


class GnomeDriver(DesktopManager):
    """Relative movement driver for GNOME Wayland using ydotool."""

    def __init__(self):
        super().__init__()
        self.ydotool_path = shutil.which('ydotool')
        self.ydotoold_path = shutil.which('ydotoold')
        self._detect_resolution()
        self.uid = os.getuid()
        self.socket = f'/run/user/{self.uid}/.ydotool_socket'
        self.ensure_daemon()
        self._tk_instance = None  # Cache for tkinter instance
        atexit.register(self._destroy_tk)

    def _destroy_tk(self):
        """Destroys the cached tkinter instance, if any."""
        try:
            if self._tk_instance is not None:
                self._tk_instance.destroy()
                self._tk_instance = None
        except Exception:
            logger.debug("Failed to destroy tkinter instance.", exc_info=True)

    def _detect_resolution(self):
        """Dynamic resolution detection for GNOME/Wayland."""
        # Try xrandr first (covers XWayland scenarios)
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

    def get_cursor_pos(self):
        """Returns cursor position via xdotool or tkinter fallback."""
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

    def move_cursor(self, x, y):
        """Emulates absolute positioning via a relative delta.

        GNOME Wayland has no absolute cursor API, so read the current
        position and move relatively. Returns nothing; failures are logged
        by move_relative().
        """
        try:
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
