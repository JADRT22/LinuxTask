import subprocess
import shutil
import os
import time
from .base import DesktopManager

class GnomeDriver(DesktopManager):
    """Simple and robust relative driver for GNOME Wayland."""
    
    def __init__(self):
        super().__init__()
        self.uid = os.getuid()
        self.socket = f'/run/user/{self.uid}/.ydotool_socket'
        self.ensure_daemon()

    def sync_delta(self, dx, dy):
        """Just accumulate relative movement."""
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
        # We return the accumulated deltas
        return int(self.virtual_x), int(self.virtual_y)
        
    def move_cursor(self, x, y):
        """This is called during playback. We don't use it in pure relative mode."""
        pass

    def move_relative(self, dx, dy):
        """Moves the mouse by a relative amount (dx, dy)."""
        if not shutil.which('ydotool'): return
        try:
            env = os.environ.copy()
            env['YDOTOOL_SOCKET'] = self.socket
            # Standard relative move
            subprocess.run(['ydotool', 'mousemove', '--', str(int(dx)), str(int(dy))], 
                           env=env, capture_output=True, check=True)
        except:
            self.ensure_daemon()
