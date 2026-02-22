import customtkinter as ctk
import time
import threading
import json
import subprocess
import os
import evdev
from tkinter import filedialog, messagebox

class LinuxTaskApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("LT")
        self.geometry("380x65")
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

        # Main Layout (Single Row)
        self.grid_columnconfigure((0, 1, 2, 3, 4, 5, 6), weight=1)
        
        btn_opts = {"width": 45, "height": 45, "compound": "top", "font": ("Arial", 9)}

        self.btn_open = ctk.CTkButton(self, text="Open", command=self.open_file, **btn_opts)
        self.btn_open.grid(row=0, column=0, padx=2, pady=5)

        self.btn_save = ctk.CTkButton(self, text="Save", command=self.save_file, **btn_opts)
        self.btn_save.grid(row=0, column=1, padx=2, pady=5)

        self.btn_rec = ctk.CTkButton(self, text="Rec", fg_color="#d32f2f", hover_color="#b71c1c", command=self.toggle_record, **btn_opts)
        self.btn_rec.grid(row=0, column=2, padx=2, pady=5)

        self.btn_play = ctk.CTkButton(self, text="Play", fg_color="#388e3c", hover_color="#1b5e20", command=self.start_playback, **btn_opts)
        self.btn_play.grid(row=0, column=3, padx=2, pady=5)

        self.btn_loop = ctk.CTkButton(self, text="Loop", fg_color="gray", command=self.toggle_loop, **btn_opts)
        self.btn_loop.grid(row=0, column=4, padx=2, pady=5)

        self.speed_var = ctk.StringVar(value="1x")
        self.speed_menu = ctk.CTkOptionMenu(self, values=["1x", "2x", "4x", "8x"], variable=self.speed_var, width=55, height=25, font=("Arial", 9))
        self.speed_menu.grid(row=0, column=5, padx=2, pady=5)

        self.btn_settings = ctk.CTkButton(self, text="⚙", width=30, height=45, fg_color="transparent", hover_color="#333333", command=self.open_settings)
        self.btn_settings.grid(row=0, column=6, padx=2, pady=5)

        self.status_label = ctk.CTkLabel(self, text="Ready", font=("Arial", 9), text_color="gray")
        self.status_label.place(x=5, y=48) # Absolute positioning for ultra compact

        threading.Thread(target=self.global_hardware_listener, daemon=True).start()

    def open_settings(self):
        settings_win = ctk.CTkToplevel(self)
        settings_win.title("Keys")
        settings_win.geometry("250x120")
        settings_win.attributes("-topmost", True)
        
        # Make it transient for the main window (helps with taskbar management and window stacking)
        settings_win.transient(self) 
        
        ctk.CTkLabel(settings_win, text="Configure Atalhos:").pack(pady=5)
        
        self.set_rec_btn = ctk.CTkButton(settings_win, text=f"REC: {self.get_key_name(self.hotkey_rec)}", command=lambda: self.start_mapping("rec", self.set_rec_btn))
        self.set_rec_btn.pack(pady=2)
        
        self.set_play_btn = ctk.CTkButton(settings_win, text=f"PLAY: {self.get_key_name(self.hotkey_play)}", command=lambda: self.start_mapping("play", self.set_play_btn))
        self.set_play_btn.pack(pady=2)

    def start_mapping(self, target, btn):
        self.is_mapping = target
        self.active_mapping_btn = btn
        btn.configure(text="Pressione uma tecla...", fg_color="orange")

    def toggle_loop(self):
        self.loop_enabled = not self.loop_enabled
        self.btn_loop.configure(fg_color="#1976d2" if self.loop_enabled else "gray")

    def get_input_devices(self):
        devices = []
        for path in evdev.list_devices():
            try:
                d = evdev.InputDevice(path)
                if evdev.ecodes.EV_KEY in d.capabilities(): devices.append(d)
            except: continue
        return devices

    def global_hardware_listener(self):
        devices = self.get_input_devices()
        for d in devices:
            threading.Thread(target=self.device_loop, args=(d,), daemon=True).start()

    def device_loop(self, device):
        try:
            for event in device.read_loop():
                if event.type == evdev.ecodes.EV_KEY:
                    data = evdev.categorize(event)
                    
                    if self.is_mapping and event.value == 1:
                        if self.is_mapping == "rec": self.hotkey_rec = event.code
                        else: self.hotkey_play = event.code
                        
                        # Captura o valor de self.is_mapping para a lambda
                        self.after(0, lambda k=data.keycode, b=self.active_mapping_btn, map_type=self.is_mapping: b.configure(text=f"{map_type.upper()}: {k}", fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"]))
                        self.is_mapping = None
                        continue

                    if event.value == 1:
                        if event.code == self.hotkey_rec: self.after(0, self.toggle_record)
                        elif event.code == self.hotkey_play: self.after(0, self.start_playback)
                        # Removed hardcoded F8 emergency stop to prevent conflicts with key remapping.

                    if self.recording and not self.stop_threads:
                        real_x, real_y = self.get_global_cursor_pos()
                        event_type = "mouse_click" if event.code in [272, 273, 274] else "keyboard"
                        self.events.append({
                            "type": event_type, "x": real_x, "y": real_y, "button": event.code,
                            "pressed": data.keystate == 1, "time": time.time() - self.start_time,
                            "key_name": data.keycode if event_type == "keyboard" else None
                        })
        except: pass

    def update_main_buttons_text(self):
        # We don't show the keys in the main buttons anymore to keep it tiny, 
        # but the logic remains.
        pass

    def get_global_cursor_pos(self):
        try:
            out = subprocess.check_output(["hyprctl", "cursorpos"]).decode().strip()
            x, y = out.split(", ")
            return int(x), int(y)
        except: return 0, 0

    def toggle_record(self):
        if self.playing: return 
        if not self.recording: self.start_recording()
        else: self.stop_recording()

    def start_recording(self):
        self.events = []
        self.recording = True
        self.stop_threads = False
        self.start_time = time.time()
        self.btn_rec.configure(text="Stop", fg_color="gray")
        self.btn_play.configure(state="disabled")
        self.status_label.configure(text="REC", text_color="red")
        threading.Thread(target=self.record_movement_thread, daemon=True).start()

    def record_movement_thread(self):
        while self.recording and not self.stop_threads:
            x, y = self.get_global_cursor_pos()
            if not self.events or self.events[-1]["x"] != x or self.events[-1]["y"] != y:
                self.events.append({"type": "move", "x": x, "y": y, "time": time.time() - self.start_time})
            time.sleep(0.01)

    def stop_recording(self):
        self.recording = False
        self.stop_threads = True
        self.btn_rec.configure(text="Rec", fg_color="#d32f2f")
        self.btn_play.configure(state="normal")
        self.status_label.configure(text="Ready", text_color="gray")

    def get_key_name(self, code):
        try: return evdev.ecodes.KEY[code] if code in evdev.ecodes.KEY else str(code)
        except: return str(code)

    def start_playback(self):
        if self.recording: return
        if self.playing:
            self.stop_all()
            return
        if not self.events: return
        
        self.playing = True
        self.btn_play.configure(text="Stop", fg_color="gray")
        self.btn_rec.configure(state="disabled")
        self.status_label.configure(text="PLAY", text_color="green")
        threading.Thread(target=self.playback_thread, daemon=True).start()

    def playback_thread(self):
        while self.playing:
            speed_multiplier = float(self.speed_var.get().replace("x", ""))
            last_time = 0
            for event in self.events:
                if not self.playing: break
                wait_time = (event["time"] - last_time) / speed_multiplier
                if wait_time > 0:
                    sleep_until = time.time() + wait_time
                    while time.time() < sleep_until:
                        if not self.playing: break
                        time.sleep(0.005)
                if not self.playing: break
                last_time = event["time"]
                if event["type"] == "move":
                    subprocess.run(["hyprctl", "dispatch", "movecursor", f"{event['x']} {event['y']}"], capture_output=True)
                elif event["type"] == "mouse_click":
                    subprocess.run(["hyprctl", "dispatch", "movecursor", f"{event['x']} {event['y']}"], capture_output=True)
                    if event["pressed"]:
                        btn = "left" if event["button"] == 272 else "right" if event["button"] == 273 else "middle"
                        subprocess.run(["wlrctl", "pointer", "click", btn], capture_output=True)
                elif event["type"] == "keyboard":
                    if event["pressed"]:
                        key = event["key_name"]
                        if isinstance(key, str):
                            subprocess.run(["wlrctl", "keyboard", "type", key.replace("KEY_", "").lower()], capture_output=True)
            if not self.loop_enabled: break
            time.sleep(0.3)
        self.playing = False
        self.after(0, self.reset_ui_after_play)

    def reset_ui_after_play(self):
        self.btn_play.configure(text="Play", state="normal", fg_color="#388e3c")
        self.btn_rec.configure(state="normal")
        self.status_label.configure(text="Ready", text_color="gray")

    def stop_all(self):
        self.playing = False
        if self.recording: self.stop_recording()

    def save_file(self):
        if not self.events: return
        file_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if file_path:
            with open(file_path, "w") as f: json.dump(self.events, f)

    def open_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if file_path:
            with open(file_path, "r") as f: self.events = json.load(f)

if __name__ == "__main__":
    app = LinuxTaskApp()
    app.mainloop()
