# -*- coding: utf-8 -*-
"""
LinuxTask - gnome.py
Description: GNOME Wayland compositor driver using ydotool.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import subprocess
import shutil
import os
import time
import logging
from .base import DesktopManager

logger = logging.getLogger(__name__)


class GnomeDriver(DesktopManager):
    """Relative movement driver for GNOME Wayland using ydotool."""

    def __init__(self):
        super().__init__()
        self._detect_resolution()
        self.uid = os.getuid()
        self.socket = f'/run/user/{self.uid}/.ydotool_socket'
        self.ensure_daemon()

    def _detect_resolution(self):
        """Dynamic resolution detection for GNOME/Wayland."""
        # Try xrandr first (covers XWayland scenarios)
        try:
            out = subprocess.check_output(
                ['xrandr'], stderr=subprocess.STDOUT
            ).decode()
            for line in out.splitlines():
                if '*' in line:
                    w, h = line.split()[0].split('x')
                    self.screen_width, self.screen_height = int(w), int(h)
                    return
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            logger.debug("xrandr failed: %s", exc)

        # Fallback: Query org.gnome.Mutter.DisplayConfig via gdbus
        try:
            import re
            cmd = [
                'gdbus', 'call', '--session', '--dest',
                'org.gnome.Mutter.DisplayConfig',
                '--object-path', '/org/gnome/Mutter/DisplayConfig',
                '--method', 'org.gnome.Mutter.DisplayConfig.GetCurrentState'
            ]
            out = subprocess.check_output(cmd).decode()
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
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            logger.debug("gdbus resolution detection failed: %s", exc)

        self.screen_width, self.screen_height = 1920, 1080
        logger.warning("Using fallback resolution: 1920x1080")

    def ensure_daemon(self):
        """Ensures ydotoold is running with our socket.

        Only kills our own socket's daemon, not all ydotoold processes.
        """
        if not shutil.which('ydotoold'):
            logger.warning("ydotoold not found. Mouse movement will not work.")
            return

        # Check if socket already exists and is functional
        if os.path.exists(self.socket):
            try:
                env = os.environ.copy()
                env['YDOTOOL_SOCKET'] = self.socket
                result = subprocess.run(
                    ['ydotool', 'mousemove', '--', '0', '0'],
                    env=env, capture_output=True, timeout=2
                )
                if result.returncode == 0:
                    logger.info("Existing ydotoold socket is functional.")
                    return
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        # Socket is stale or missing — clean up and restart
        try:
            if os.path.exists(self.socket):
                os.remove(self.socket)
        except OSError as exc:
            logger.warning("Could not remove stale socket: %s", exc)

        try:
            subprocess.Popen(
                ['ydotoold', '--socket-path', self.socket],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            for _ in range(30):
                if os.path.exists(self.socket):
                    os.chmod(self.socket, 0o666)
                    logger.info("ydotoold started with socket: %s", self.socket)
                    return
                time.sleep(0.1)
            logger.error("ydotoold started but socket never appeared.")
        except FileNotFoundError:
            logger.error("ydotoold binary not found.")
        except OSError as exc:
            logger.error("Failed to start ydotoold: %s", exc)

    def get_cursor_pos(self):
        """Returns dummy tracked position (absolute pos unavailable on Wayland)."""
        return 0, 0

    def move_cursor(self, x, y):
        """Absolute cursor positioning is not supported on GNOME Wayland.

        Use move_relative() instead.
        """
        logger.warning(
            "move_cursor() is not supported on GNOME Wayland. "
            "Use move_relative() instead."
        )

    def move_relative(self, dx, dy):
        """Moves cursor by relative offset using ydotool."""
        if not shutil.which('ydotool'):
            return False
        try:
            env = os.environ.copy()
            env['YDOTOOL_SOCKET'] = self.socket
            subprocess.run(
                ['ydotool', 'mousemove', '--',
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
        """Handles mouse button via ydotool click.
        Note: ydotool 'click' does press+release. We use it as a fallback.
        """
        if not pressed:
            return False # ydotool click handles both, so we 'handle' it on press

        # evdev: 272=LEFT, 273=RIGHT, 274=MIDDLE
        # ydotool: 0x40=LEFT, 0x41=RIGHT, 0x42=MIDDLE
        ydo_btn = None
        if button == 272: ydo_btn = "0x40"
        elif button == 273: ydo_btn = "0x41"
        elif button == 274: ydo_btn = "0x42"

        if not ydo_btn or not shutil.which('ydotool'):
            return False

        try:
            env = os.environ.copy()
            env['YDOTOOL_SOCKET'] = self.socket
            subprocess.run(
                ['ydotool', 'click', ydo_btn],
                env=env, capture_output=True, check=True
            )
            return True
        except subprocess.CalledProcessError as exc:
            logger.error("ydotool click failed: %s", exc)
            return False

    def scroll(self, direction, clicks=1):
        """Performs scroll via ydotool."""
        if not shutil.which('ydotool'):
            return
        try:
            env = os.environ.copy()
            env['YDOTOOL_SOCKET'] = self.socket
            # ydotool mousemove uses --wheel for scroll
            value = clicks if direction == 'up' else -clicks
            subprocess.run(
                ['ydotool', 'mousemove', '--wheel', '--',
                 '0', str(value)],
                env=env, capture_output=True, check=True
            )
        except subprocess.CalledProcessError as exc:
            logger.error("ydotool scroll failed: %s", exc)
