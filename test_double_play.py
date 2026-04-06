import sys
import os
sys.path.insert(0, os.path.abspath('src'))
from main import LinuxTaskApp
import threading, time

app = LinuxTaskApp()
app.events = [{'type': 'rel', 'dx': 10, 'dy': 10, 'time': 0.1}]
app.start_cursor_pos = (100, 100)

print("Starting playback 1...")
app.handle_play_key()
time.sleep(1)
print(f"Playing status: {app.playing}")

print("Starting playback 2...")
app.handle_play_key()
time.sleep(1)
print(f"Playing status: {app.playing}")

app.destroy()
