import customtkinter as ctk
import time
import threading
import json
import os
import evdev
import random
from evdev import ecodes as e
from tkinter import filedialog, messagebox
from drivers.factory import AutoDetectDriver

class LinuxTaskApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.manager = AutoDetectDriver()
        self.title("LinuxTask v2.2 - Pure Relative")
        self.geometry("400x50")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.recording = False
        self.playing = False
        self.events = []
        self.start_time = 0
        self.stop_threads = False
        self.loop_enabled = False
        self.humanize_enabled = ctk.BooleanVar(value=False)
        self.hotkey_rec = 66
        self.hotkey_play = 67
        self.is_mapping = None
        self.uinput_device = None
        self.init_uinput()

        self.grid_columnconfigure((0, 1, 2, 3, 4, 5, 6), weight=1)
        self.grid_rowconfigure(0, weight=1)
        btn_opts = {"width": 40, "height": 40, "font": ("Segoe UI Symbol", 16), "corner_radius": 5}
        
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

        threading.Thread(target=self.global_hardware_listener, daemon=True).start()

    def init_uinput(self):
        try:
            cap = {e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE] + list(range(1, 512))}
            self.uinput_device = evdev.UInput(cap, name="LinuxTask-Virtual", vendor=0x1234, product=0x5678)
        except: pass

    def open_settings(self):
        self.settings_win = ctk.CTkToplevel(self)
        self.settings_win.title("Settings")
        self.settings_win.geometry("300x250")
        self.settings_win.attributes("-topmost", True)
        self.settings_frame = ctk.CTkFrame(self.settings_win, fg_color="#2b2b2b")
        self.settings_frame.pack(fill="both", expand=True)
        ctk.CTkLabel(self.settings_frame, text="Global Hotkeys", font=("Arial", 14, "bold")).pack(pady=10)
        self.lbl_rec = ctk.CTkButton(self.settings_frame, text=f"Record: {self.get_key_name(self.hotkey_rec)}", command=lambda: self.start_mapping("rec", self.lbl_rec))
        self.lbl_rec.pack(pady=5, fill="x", padx=20)
        self.lbl_play = ctk.CTkButton(self.settings_frame, text=f"Play/Stop: {self.get_key_name(self.hotkey_play)}", command=lambda: self.start_mapping("play", self.lbl_play))
        self.lbl_play.pack(pady=5, fill="x", padx=20)
        ctk.CTkCheckBox(self.settings_frame, text="Humanize", variable=self.humanize_enabled).pack(pady=10)

    def start_mapping(self, mode, btn):
        self.is_mapping = mode
        btn.configure(text="Press any key...", fg_color="#FFA500")

    def toggle_loop(self):
        self.loop_enabled = not self.loop_enabled
        self.btn_loop.configure(fg_color="#1976d2" if self.loop_enabled else "#333333")

    def get_input_devices(self):
        return [evdev.InputDevice(path) for path in evdev.list_devices()]

    def global_hardware_listener(self):
        for d in self.get_input_devices():
            threading.Thread(target=self.device_loop, args=(d,), daemon=True).start()

    def device_loop(self, dev):
        try:
            for event in dev.read_loop():
                if event.type == e.EV_REL and self.recording:
                    dx = event.value if event.code == e.REL_X else 0
                    dy = event.value if event.code == e.REL_Y else 0
                    self.events.append({"type": "rel", "dx": dx, "dy": dy, "time": time.time() - self.start_time})

                if event.type == e.EV_KEY:
                    if self.is_mapping and event.value == 1:
                        if self.is_mapping == "rec": self.hotkey_rec = event.code
                        else: self.hotkey_play = event.code
                        self.is_mapping = None; continue

                    if event.value == 1:
                        if event.code == self.hotkey_rec: self.after(0, self.toggle_record)
                        elif event.code == self.hotkey_play: self.after(0, self.handle_play_key)

                    if self.recording and not self.stop_threads:
                        if event.code not in [self.hotkey_rec, self.hotkey_play]:
                            self.events.append({"type": "key", "code": event.code, "val": event.value, "time": time.time() - self.start_time})
        except: pass

    def toggle_record(self):
        if self.playing: return
        if not self.recording:
            self.recording = True; self.events = []; self.start_time = time.time()
            self.btn_rec.configure(text="⏹", fg_color="#b71c1c")
        else:
            self.recording = False
            self.btn_rec.configure(text="⏺", fg_color="#d32f2f")

    def handle_play_key(self):
        if self.playing: self.playing = False
        else: self.start_playback()

    def start_playback(self):
        if self.recording or not self.events: return
        self.playing = True
        self.btn_play.configure(text="⏹", fg_color="#b71c1c")
        threading.Thread(target=self.playback_thread, daemon=True).start()

    def playback_thread(self):
        try:
            while self.playing:
                start_p = time.time()
                speed = float(self.speed_var.get().replace("x", ""))
                for ev in self.events:
                    if not self.playing: break
                    while time.time() < start_p + (ev['time'] / speed): time.sleep(0.001)
                    if ev['type'] == "rel":
                        self.manager.move_relative(ev['dx'], ev['dy'])
                    elif ev['type'] == "key":
                        self.uinput_device.write(e.EV_KEY, ev['code'], ev['val'])
                        self.uinput_device.syn()
                if not self.loop_enabled: break
        except: pass
        finally:
            self.playing = False
            self.after(0, lambda: self.btn_play.configure(text="⏵", fg_color="#388e3c"))

    def get_key_name(self, code): return evdev.ecodes.KEY.get(code, str(code))
    def save_file(self):
        f = filedialog.asksaveasfilename(defaultextension=".json")
        if f: 
            with open(f, 'w') as fp: json.dump(self.events, fp)
    def open_file(self):
        f = filedialog.askopenfilename()
        if f:
            with open(f, 'r') as fp: self.events = json.load(fp)

if __name__ == "__main__":
    app = LinuxTaskApp(); app.mainloop()
