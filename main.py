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

        self.title("LinuxTask")
        self.geometry("600x120")
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
        
        # Default Hotkeys (evdev codes: F8=66, F9=67)
        self.hotkey_rec = 66  # F8
        self.hotkey_play = 67 # F9
        self.is_mapping = None

        # UI Layout
        self.grid_columnconfigure((0, 1, 2, 3, 4, 5, 6), weight=1)
        self.grid_rowconfigure((0, 1), weight=1)

        # Row 0: Control Buttons
        self.btn_open = ctk.CTkButton(self, text="📂", width=40, command=self.open_file)
        self.btn_open.grid(row=0, column=0, padx=2, pady=5)

        self.btn_save = ctk.CTkButton(self, text="💾", width=40, command=self.save_file)
        self.btn_save.grid(row=0, column=1, padx=2, pady=5)

        self.btn_rec = ctk.CTkButton(self, text="● REC (F8)", width=85, fg_color="#d32f2f", hover_color="#b71c1c", command=self.toggle_record)
        self.btn_rec.grid(row=0, column=2, padx=2, pady=5)

        self.btn_play = ctk.CTkButton(self, text="▶ PLAY (F9)", width=85, fg_color="#388e3c", hover_color="#1b5e20", command=self.start_playback)
        self.btn_play.grid(row=0, column=3, padx=2, pady=5)

        self.btn_loop = ctk.CTkButton(self, text="🔁 LOOP", width=75, fg_color="gray", command=self.toggle_loop)
        self.btn_loop.grid(row=0, column=4, padx=2, pady=5)

        self.btn_stop = ctk.CTkButton(self, text="■ STOP", width=75, state="disabled", command=self.stop_all)
        self.btn_stop.grid(row=0, column=5, padx=2, pady=5)

        self.speed_var = ctk.StringVar(value="1x")
        self.speed_menu = ctk.CTkOptionMenu(self, values=["1x", "2x", "4x", "8x"], variable=self.speed_var, width=65)
        self.speed_menu.grid(row=0, column=6, padx=2, pady=5)

        # Row 1: Key Mapping
        self.btn_set_rec = ctk.CTkButton(self, text="Set REC Key", width=120, height=25, command=lambda: self.start_mapping("rec"))
        self.btn_set_rec.grid(row=1, column=2, padx=2, pady=5)

        self.btn_set_play = ctk.CTkButton(self, text="Set PLAY Key", width=120, height=25, command=lambda: self.start_mapping("play"))
        self.btn_set_play.grid(row=1, column=3, padx=2, pady=5)

        self.status_label = ctk.CTkLabel(self, text="Ready", font=("Arial", 11, "bold"))
        self.status_label.grid(row=1, column=0, columnspan=2, padx=5)

        # Start Global Hardware Listener
        threading.Thread(target=self.global_hardware_listener, daemon=True).start()

    def start_mapping(self, target):
        self.is_mapping = target
        self.status_label.configure(text=f"Press key for {target.upper()}...", text_color="orange")

    def toggle_loop(self):
        self.loop_enabled = not self.loop_enabled
        self.btn_loop.configure(fg_color="#1976d2" if self.loop_enabled else "gray")

    def get_input_devices(self):
        devices = []
        for path in evdev.list_devices():
            try:
                d = evdev.InputDevice(path)
                caps = d.capabilities()
                if evdev.ecodes.EV_KEY in caps:
                    devices.append(d)
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
                    
                    # Key Mapping Mode
                    if self.is_mapping and event.value == 1:
                        if self.is_mapping == "rec":
                            self.hotkey_rec = event.code
                            self.btn_rec.configure(text=f"● REC ({data.keycode})")
                        else:
                            self.hotkey_play = event.code
                            self.btn_play.configure(text=f"▶ PLAY ({data.keycode})")
                        
                        self.is_mapping = None
                        self.after(0, lambda: self.status_label.configure(text="Hotkey updated!", text_color="white"))
                        continue

                    # Global Listeners (REC / PLAY / STOP)
                    if event.value == 1: # Key Down
                        if event.code == self.hotkey_rec:
                            self.after(0, self.toggle_record)
                        elif event.code == self.hotkey_play:
                            self.after(0, self.start_playback)
                        elif event.code == evdev.ecodes.KEY_F8: # F8 emergency stop
                            self.after(0, self.stop_all)

                    # Event Recording
                    if self.recording and not self.stop_threads:
                        real_x, real_y = self.get_global_cursor_pos()
                        event_type = "mouse_click" if event.code in [272, 273, 274] else "keyboard"
                        self.events.append({
                            "type": event_type,
                            "x": real_x,
                            "y": real_y,
                            "button": event.code,
                            "pressed": data.keystate == 1,
                            "time": time.time() - self.start_time,
                            "key_name": data.keycode if event_type == "keyboard" else None
                        })
        except: pass

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
        self.btn_rec.configure(text="■ STOP REC", fg_color="gray")
        self.btn_play.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status_label.configure(text="RECORDING...", text_color="red")
        
        # Ultra Smooth sampling (100Hz)
        threading.Thread(target=self.record_movement_thread, daemon=True).start()

    def record_movement_thread(self):
        while self.recording and not self.stop_threads:
            x, y = self.get_global_cursor_pos()
            if not self.events or self.events[-1]["x"] != x or self.events[-1]["y"] != y:
                self.events.append({
                    "type": "move",
                    "x": x,
                    "y": y,
                    "time": time.time() - self.start_time
                })
            time.sleep(0.01)

    def stop_recording(self):
        self.recording = False
        self.stop_threads = True
        self.btn_rec.configure(text=f"● REC ({self.get_key_name(self.hotkey_rec)})", fg_color="#d32f2f")
        self.btn_play.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.status_label.configure(text="Ready", text_color="white")

    def get_key_name(self, code):
        try: return evdev.ecodes.KEY[code] if code in evdev.ecodes.KEY else str(code)
        except: return str(code)

    def start_playback(self):
        if not self.events or self.recording: return
        self.playing = True
        self.btn_play.configure(state="disabled")
        self.btn_rec.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status_label.configure(text="PLAYING...", text_color="green")
        threading.Thread(target=self.playback_thread, daemon=True).start()

    def playback_thread(self):
        while self.playing:
            speed_multiplier = float(self.speed_var.get().replace("x", ""))
            last_time = 0
            
            for event in self.events:
                if not self.playing: break
                
                # Time Sync
                wait_time = (event["time"] - last_time) / speed_multiplier
                if wait_time > 0: time.sleep(wait_time)
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
        self.btn_play.configure(state="normal")
        self.btn_rec.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.status_label.configure(text="Ready", text_color="white")

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
