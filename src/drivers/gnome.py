# -*- coding: utf-8 -*-
"""
LinuxTask - gnome.py
Description: GNOME Wayland compositor driver.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import subprocess
import shutil
import os
import time
from .base import DesktopManager

class GnomeDriver(DesktopManager):
    """Simple and robust relative driver for GNOME Wayland."""
    
    def __init__(self):
        super().__init__()
        self._detect_resolution()
        self.uid = os.getuid()
        self.socket = f'/run/user/{self.uid}/.ydotool_socket'
        self.ensure_daemon()

    def _detect_resolution(self):
        """Dynamic resolution detection for GNOME/Wayland."""
        # Try xrandr first (fastest, covers most XWayland scenarios)
        try:
            out = subprocess.check_output(['xrandr'], stderr=subprocess.STDOUT).decode()
            for line in out.splitlines():
                if '*' in line:
                    w, h = line.split()[0].split('x')
                    self.screen_width, self.screen_height = int(w), int(h)
                    return
        except: pass

        # Fallback: Query org.gnome.Mutter.DisplayConfig via gdbus
        try:
            cmd = [
                'gdbus', 'call', '--session', '--dest',
                'org.gnome.Mutter.DisplayConfig',
                '--object-path', '/org/gnome/Mutter/DisplayConfig',
                '--method', 'org.gnome.Mutter.DisplayConfig.GetCurrentState'
            ]
            out = subprocess.check_output(cmd).decode()
            if "'is-current': <true>" in out:
                import re
                # Pattern: 'NAME', WIDTH, HEIGHT, ...
                pattern = (
                    r"'\d+x\d+@[\d\.]+',\s+(\d+),\s+(\d+).*?"
                    r"'is-current':\s+<true>"
                )
                match = re.search(pattern, out, re.DOTALL)
                if match:
                    self.screen_width = int(match.group(1))
                    self.screen_height = int(match.group(2))
                    return
        except: pass

        self.screen_width, self.screen_height = 1920, 1080

    def sync_delta(self, dx, dy):
        self.virtual_x += dx
        self.virtual_y += dy

    def ensure_daemon(self):
        try:
            subprocess.run(['pkill', '-9', 'ydotoold'], capture_output=True)
            if os.path.exists(self.socket): os.remove(self.socket)
        except: pass
        try:
            subprocess.Popen(['ydotoold', '--socket-path', self.socket], 
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(30):
                if os.path.exists(self.socket):
                    os.chmod(self.socket, 0o666)
                    return
                time.sleep(0.1)
        except: pass

    def get_cursor_pos(self):
        return int(self.virtual_x), int(self.virtual_y)
        
    def move_cursor(self, x, y):
        pass

    def move_relative(self, dx, dy):
        if not shutil.which('ydotool'): return
        try:
            env = os.environ.copy()
            env['YDOTOOL_SOCKET'] = self.socket
            subprocess.run(['ydotool', 'mousemove', '--', str(int(dx)), str(int(dy))], 
                           env=env, capture_output=True, check=True)
        except:
            self.ensure_daemon()
