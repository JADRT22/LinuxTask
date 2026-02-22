import customtkinter as ctk
import time
import threading
import json
import subprocess
import os
import evdev
from evdev import ecodes as e
from tkinter import filedialog, messagebox

class LinuxTaskApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("LinuxTask v1.6")
        self.geometry("400x50")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # State Variables
        self.recording = False
        self.playing = False
        self.events = []
        self.start_time = 0
        self.stop_threads = False
        self.loop_enabled = False
        
        self.hotkey_rec = 66  # F8
        self.hotkey_play = 67 # F9
        self.is_mapping = None
        self.uinput_device = None

        # Initialize UInput
        self.init_uinput()

        # Main Layout (Compact Toolbar)
        self.grid_columnconfigure((0, 1, 2, 3, 4, 5, 6), weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Styles
        btn_opts = {"width": 40, "height": 40, "font": ("Segoe UI Symbol", 16), "corner_radius": 5}
        
        # Icons: 📂 💾 ⏺ ⏵ ⚙ 🔁
        self.btn_open = ctk.CTkButton(self, text="📂", fg_color="#333333", hover_color="#444444", command=self.open_file, **btn_opts)
        self.btn_open.grid(row=0, column=0, padx=2, pady=2)
        
        self.btn_save = ctk.CTkButton(self, text="💾", fg_color="#333333", hover_color="#444444", command=self.save_file, **btn_opts)
        self.btn_save.grid(row=0, column=1, padx=2, pady=2)

        self.btn_rec = ctk.CTkButton(self, text="⏺", fg_color="#d32f2f", hover_color="#b71c1c", command=self.toggle_record, **btn_opts)
        self.btn_rec.grid(row=0, column=2, padx=2, pady=2)

        self.btn_play = ctk.CTkButton(self, text="⏵", fg_color="#388e3c", hover_color="#1b5e20", command=self.start_playback, **btn_opts)
        self.btn_play.grid(row=0, column=3, padx=2, pady=2)

        self.btn_loop = ctk.CTkButton(self, text="🔁", fg_color="#333333", hover_color="#444444", command=self.toggle_loop, **btn_opts)
        self.btn_loop.grid(row=0, column=4, padx=2, pady=2)

        self.speed_var = ctk.StringVar(value="1x")
        self.speed_menu = ctk.CTkOptionMenu(self, values=["0.5x", "1x", "2x", "4x", "10x"], variable=self.speed_var, width=60, height=25, font=("Arial", 10))
        self.speed_menu.grid(row=0, column=5, padx=2, pady=2)

        self.btn_settings = ctk.CTkButton(self, text="⚙", fg_color="transparent", hover_color="#222222", width=30, command=self.open_settings)
        self.btn_settings.grid(row=0, column=6, padx=2, pady=2)

        # Tooltips / Status (Optional console output or simple label overlay if needed, 
        # but keeping it minimal as requested "TinyTask style")

        threading.Thread(target=self.global_hardware_listener, daemon=True).start()

    def init_uinput(self):
        try:
            # Capabilities: Mouse buttons + All Keys
            cap = {
                e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE, e.BTN_SIDE, e.BTN_EXTRA] + list(range(1, 512)),
                e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL],
                e.EV_ABS: [e.ABS_X, e.ABS_Y]
            }
            self.uinput_device = evdev.UInput(cap, name="LinuxTask-Virtual-Input", version=0x1)
        except Exception as ex:
            print(f"UInput Error: {ex}")
            self.uinput_device = None

    def open_settings(self):
        win = ctk.CTkToplevel(self)
        win.title("Settings")
        win.geometry("300x200")
        win.attributes("-topmost", True)
        
        ctk.CTkLabel(win, text="Global Hotkeys", font=("Arial", 14, "bold")).pack(pady=10)
        
        self.lbl_rec = ctk.CTkButton(win, text=f"Record: {self.get_key_name(self.hotkey_rec)}", command=lambda: self.start_mapping("rec", self.lbl_rec))
        self.lbl_rec.pack(pady=5, fill="x", padx=20)
        
        self.lbl_play = ctk.CTkButton(win, text=f"Play/Stop: {self.get_key_name(self.hotkey_play)}", command=lambda: self.start_mapping("play", self.lbl_play))
        self.lbl_play.pack(pady=5, fill="x", padx=20)

        ctk.CTkButton(win, text="Create Desktop Entry", fg_color="#555555", command=self.create_desktop_shortcut).pack(pady=15)

    def create_desktop_shortcut(self):
        try:
            home = os.path.expanduser("~")
            app_dir = os.path.abspath(os.path.dirname(__file__))
            desktop_path = os.path.join(home, ".local/share/applications/LinuxTask.desktop")
            
            content = f"""[Desktop Entry]
Name=LinuxTask
Exec={os.path.join(app_dir, 'run.sh')}
Icon={os.path.join(app_dir, 'icon.png')}
Type=Application
Categories=Utility;
Comment=Macro Recorder
"""
            with open(desktop_path, "w") as f: f.write(content)
            messagebox.showinfo("Success", "Shortcut created! Look in your app menu.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def start_mapping(self, mode, btn):
        self.is_mapping = mode
        self.map_btn = btn
        btn.configure(text="Press any key...", fg_color="#FFA500")

    def toggle_loop(self):
        self.loop_enabled = not self.loop_enabled
        self.btn_loop.configure(fg_color="#1976d2" if self.loop_enabled else "#333333")

    def get_input_devices(self):
        return [evdev.InputDevice(path) for path in evdev.list_devices()]

    def global_hardware_listener(self):
        # Simple watcher for all input devices
        devices = self.get_input_devices()
        for d in devices:
            threading.Thread(target=self.device_loop, args=(d,), daemon=True).start()

    def device_loop(self, dev):
        try:
            for event in dev.read_loop():
                if event.type == e.EV_KEY:
                    # Mapping Mode
                    if self.is_mapping and event.value == 1:
                        code = event.code
                        name = evdev.ecodes.KEY.get(code, str(code))
                        if self.is_mapping == "rec":
                            self.hotkey_rec = code
                            self.map_btn.configure(text=f"Record: {name}", fg_color="#3B8ED0")
                        else:
                            self.hotkey_play = code
                            self.map_btn.configure(text=f"Play/Stop: {name}", fg_color="#3B8ED0")
                        self.is_mapping = None
                        continue

                    # Hotkey Action (Press only)
                    if event.value == 1:
                        if event.code == self.hotkey_rec:
                            self.after(0, self.toggle_record)
                        elif event.code == self.hotkey_play:
                            self.after(0, self.handle_play_key)

                    # Recording Logic
                    if self.recording and not self.stop_threads:
                        # Capture mouse buttons and keys
                        if event.code in [self.hotkey_rec, self.hotkey_play]: continue # Don't record control keys
                        
                        # Get Mouse Pos for context
                        x, y = self.get_cursor_pos()
                        self.events.append({
                            "type": "input",
                            "code": event.code,
                            "val": event.value,
                            "x": x, "y": y,
                            "time": time.time() - self.start_time
                        })
        except: pass

    def get_cursor_pos(self):
        try:
            # Fast hyprctl call
            out = subprocess.check_output("hyprctl cursorpos", shell=True).decode().strip()
            x, y = out.split(", ")
            return int(x), int(y)
        except: return 0, 0

    def toggle_record(self):
        if self.playing: return
        if not self.recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        self.recording = True
        self.stop_threads = False
        self.events = []
        self.start_time = time.time()
        self.btn_rec.configure(text="⏹", fg_color="#b71c1c") # Stop Icon
        self.btn_play.configure(state="disabled")
        threading.Thread(target=self.record_motion_thread, daemon=True).start()

    def stop_recording(self):
        self.recording = False
        self.stop_threads = True
        self.btn_rec.configure(text="⏺", fg_color="#d32f2f")
        self.btn_play.configure(state="normal")

    def record_motion_thread(self):
        # Poll mouse position at ~60Hz-100Hz
        last_x, last_y = -1, -1
        while self.recording and not self.stop_threads:
            x, y = self.get_cursor_pos()
            if x != last_x or y != last_y:
                self.events.append({
                    "type": "move",
                    "x": x, "y": y,
                    "time": time.time() - self.start_time
                })
                last_x, last_y = x, y
            time.sleep(0.015) # ~66Hz

    def handle_play_key(self):
        if self.playing:
            self.stop_playback()
        else:
            self.start_playback()

    def start_playback(self):
        if self.recording or not self.events: return
        self.playing = True
        self.btn_play.configure(text="⏹", fg_color="#b71c1c")
        self.btn_rec.configure(state="disabled")
        threading.Thread(target=self.playback_thread, daemon=True).start()

    def stop_playback(self):
        self.playing = False
        # UI reset happens in thread finish or here immediately?
        # Thread checks self.playing, so it will stop.

    def playback_thread(self):
        if not self.uinput_device:
            print("UInput not active")
            self.playing = False
            self.after(0, self.reset_ui)
            return

        try:
            while self.playing:
                start_play_time = time.time()
                # Sort events by time just in case motion/input threads desync
                sorted_events = sorted(self.events, key=lambda k: k['time'])
                
                speed = float(self.speed_var.get().replace("x", ""))
                
                for ev in sorted_events:
                    if not self.playing: break
                    
                    # Calculate wait
                    target_time = start_play_time + (ev['time'] / speed)
                    now = time.time()
                    wait = target_time - now
                    
                    if wait > 0:
                        time.sleep(wait)

                    if ev['type'] == "move":
                        subprocess.run(f"hyprctl dispatch movecursor {ev['x']} {ev['y']}", shell=True)
                    elif ev['type'] == "input":
                        # If it's a click, ensure position (optional but good)
                        if ev['code'] in [272, 273, 274]: # Mouse Btns
                             subprocess.run(f"hyprctl dispatch movecursor {ev['x']} {ev['y']}", shell=True)
                        
                        self.uinput_device.write(e.EV_KEY, ev['code'], ev['val'])
                        self.uinput_device.syn()

                if not self.loop_enabled: break
                time.sleep(0.5)

        except Exception as ex:
            print(f"Playback Error: {ex}")
        
        self.playing = False
        self.after(0, self.reset_ui)

    def reset_ui(self):
        self.btn_play.configure(text="⏵", fg_color="#388e3c")
        self.btn_rec.configure(state="normal")

    def get_key_name(self, code):
        return evdev.ecodes.KEY.get(code, f"Key_{code}")

    def save_file(self):
        f = filedialog.asksaveasfilename(defaultextension=".json")
        if f:
            with open(f, 'w') as fp: json.dump(self.events, fp)

    def open_file(self):
        f = filedialog.askopenfilename()
        if f:
            with open(f, 'r') as fp: self.events = json.load(fp)

if __name__ == "__main__":
    app = LinuxTaskApp()
    app.mainloop()
