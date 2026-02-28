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
        
        # Desktop Environment Manager
        self.manager = AutoDetectDriver()

        self.title("LinuxTask v2.2")
        self.geometry("400x50")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # State
        self.recording = False
        self.playing = False
        self.events = []
        self.start_time = 0
        self.stop_threads = False
        self.loop_enabled = False
        self.humanize_enabled = ctk.BooleanVar(value=False)
        
        self.hotkey_rec = 66  # F8
        self.hotkey_play = 67 # F9
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
            cap = {
                e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE, e.BTN_SIDE, e.BTN_EXTRA] + list(range(1, 512)),
                e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL],
            }
            self.uinput_device = evdev.UInput(cap, name="LinuxTask-Virtual-Input", version=0x1)
        except Exception as ex:
            print(f"UInput Error: {ex}")
            self.uinput_device = None

    def open_settings(self):
        if hasattr(self, 'settings_win') and self.settings_win.winfo_exists():
            self.settings_win.lift()
            self.settings_win.focus()
            return

        self.settings_win = ctk.CTkToplevel(self)
        self.settings_win.title("Settings")
        self.settings_win.geometry("300x250")
        self.settings_win.attributes("-topmost", True)
        self.settings_win.transient(self)
        
        self.settings_frame = ctk.CTkFrame(self.settings_win, fg_color="#2b2b2b", corner_radius=0)
        self.settings_frame.pack(fill="both", expand=True)
        
        ctk.CTkLabel(self.settings_frame, text="Global Hotkeys", font=("Arial", 14, "bold"), text_color="white").pack(pady=10)
        
        self.lbl_rec = ctk.CTkButton(self.settings_frame, text=f"Record: {self.get_key_name(self.hotkey_rec)}", fg_color="#1f6aa5", hover_color="#144870", command=lambda: self.start_mapping("rec", self.lbl_rec))
        self.lbl_rec.pack(pady=5, fill="x", padx=20)
        
        self.lbl_play = ctk.CTkButton(self.settings_frame, text=f"Play/Stop: {self.get_key_name(self.hotkey_play)}", fg_color="#1f6aa5", hover_color="#144870", command=lambda: self.start_mapping("play", self.lbl_play))
        self.lbl_play.pack(pady=5, fill="x", padx=20)

        ctk.CTkCheckBox(self.settings_frame, text="Humanize (Anti-Bot Jitter)", variable=self.humanize_enabled, text_color="white", hover_color="#1f6aa5").pack(pady=10)
        ctk.CTkButton(self.settings_frame, text="Create Desktop Entry", fg_color="#555555", hover_color="#333333", command=self.create_desktop_shortcut).pack(pady=15)
        self.settings_win.after(100, lambda: self.settings_win.focus())

    def create_desktop_shortcut(self):
        try:
            home = os.path.expanduser("~")
            app_dir = os.path.abspath(os.path.dirname(__file__))
            desktop_path = os.path.join(home, ".local/share/applications/linuxtask.desktop")
            content = f"[Desktop Entry]\nName=LinuxTask\nComment=Macro Recorder Minimalista\nExec={os.path.join(app_dir, 'run.sh')}\nIcon=input-mouse\nTerminal=false\nType=Application\nCategories=Utility;Automation;\nStartupNotify=true\nPath={app_dir}\n"
            with open(desktop_path, "w") as f: f.write(content)
            messagebox.showinfo("Success", "Shortcut updated!")
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
        devices = self.get_input_devices()
        for d in devices:
            threading.Thread(target=self.device_loop, args=(d,), daemon=True).start()

    def device_loop(self, dev):
        try:
            for event in dev.read_loop():
                if event.type == e.EV_KEY:
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

                    if event.value == 1:
                        if event.code == self.hotkey_rec:
                            self.after(0, self.toggle_record)
                        elif event.code == self.hotkey_play:
                            self.after(0, self.handle_play_key)

                    if self.recording and not self.stop_threads:
                        if event.code in [self.hotkey_rec, self.hotkey_play]: continue
                        x, y = self.get_cursor_pos()
                        self.events.append({"type": "input", "code": event.code, "val": event.value, "x": x, "y": y, "time": time.time() - self.start_time})
        except: pass

    def get_cursor_pos(self):
        return self.manager.get_cursor_pos()

    def toggle_record(self):
        if self.playing: return
        if not self.recording: self.start_recording()
        else: self.stop_recording()

    def start_recording(self):
        self.recording = True
        self.stop_threads = False
        self.events = []
        self.start_time = time.time()
        self.btn_rec.configure(text="⏹", fg_color="#b71c1c")
        self.btn_play.configure(state="disabled")
        threading.Thread(target=self.record_motion_thread, daemon=True).start()

    def stop_recording(self):
        self.recording = False
        self.stop_threads = True
        self.btn_rec.configure(text="⏺", fg_color="#d32f2f")
        self.btn_play.configure(state="normal")

    def record_motion_thread(self):
        last_x, last_y = -1, -1
        while self.recording and not self.stop_threads:
            x, y = self.get_cursor_pos()
            if x != last_x or y != last_y:
                self.events.append({"type": "move", "x": x, "y": y, "time": time.time() - self.start_time})
                last_x, last_y = x, y
            time.sleep(0.015)

    def handle_play_key(self):
        if self.playing: self.stop_playback()
        else: self.start_playback()

    def start_playback(self):
        if self.recording or not self.events: return
        self.playing = True
        self.btn_play.configure(text="⏹", fg_color="#b71c1c")
        self.btn_rec.configure(state="disabled")
        threading.Thread(target=self.playback_thread, daemon=True).start()

    def stop_playback(self):
        self.playing = False
        self.release_all_safe()

    def release_all_safe(self):
        if not self.uinput_device: return
        
        # Release mouse buttons (BTN_LEFT to BTN_SIDE) and common keys
        mouse_buttons = [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE, e.BTN_SIDE, e.BTN_EXTRA]
        for code in mouse_buttons + list(range(1, 200)):
            try:
                self.uinput_device.write(e.EV_KEY, code, 0)
            except: pass
        self.uinput_device.syn()

    def playback_thread(self):
        if not self.uinput_device:
            print("UInput not active")
            self.after(0, self.reset_ui)
            return

        if not self.events:
            self.playing = False
            self.after(0, self.reset_ui)
            return

        try:
            while self.playing:
                start_play_time = time.time()
                sorted_events = sorted(self.events, key=lambda k: k.get('time', 0))
                speed = float(self.speed_var.get().replace("x", ""))
                is_human = self.humanize_enabled.get()
                last_recorded_x, last_recorded_y = None, None

                for ev in sorted_events:
                    if not self.playing: break
                    target_time = start_play_time + (ev['time'] / speed)
                    if is_human: target_time += random.uniform(0, 0.002)
                    while time.time() < target_time:
                        if not self.playing: break
                        time.sleep(0.001)

                    if not self.playing: break
                    curr_x, curr_y = ev.get('x', 0), ev.get('y', 0)

                    if ev['type'] == "move":
                        if last_recorded_x is not None:
                            dx, dy = curr_x - last_recorded_x, curr_y - last_recorded_y
                            self.uinput_device.write(e.EV_REL, e.REL_X, dx)
                            self.uinput_device.write(e.EV_REL, e.REL_Y, dy)
                            self.uinput_device.syn()
                        else:
                            self.manager.move_cursor(curr_x, curr_y)
                        last_recorded_x, last_recorded_y = curr_x, curr_y
                    elif ev['type'] == "input":
                        if ev.get('code') in [272, 273, 274]:
                             self.manager.move_cursor(curr_x, curr_y)
                        self.uinput_device.write(e.EV_KEY, ev['code'], ev['val'])
                        self.uinput_device.syn()
                        last_recorded_x, last_recorded_y = curr_x, curr_y

                if not self.loop_enabled: break
                time.sleep(0.1)
        except Exception as ex: print(f"Playback Error: {ex}")
        finally:
            self.release_all_safe()
        
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
