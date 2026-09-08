# -*- coding: utf-8 -*-
"""
LinuxTask - main.py
Description: Main application loop and UI.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("LinuxTask")

try:
    import customtkinter as ctk
    import evdev
    from evdev import ecodes as e
except ImportError:
    print("Error: Missing dependencies (customtkinter or evdev).",
          file=sys.stderr)
    print("Please run install.sh or install python-customtkinter "
          "via your package manager.", file=sys.stderr)
    sys.exit(1)

import time
import random
import threading
import json
import os
from tkinter import filedialog
from drivers.factory import AutoDetectDriver


class LinuxTaskApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.manager = AutoDetectDriver()
        env_name = self.manager.__class__.__name__.replace("Driver", "")
        if env_name == "X11": env_name = "X11 Edition"
        elif env_name == "Gnome": env_name = "GNOME Edition"
        elif env_name == "KdeWayland": env_name = "KDE Wayland Edition"
        elif env_name == "Hyprland": env_name = "Hyprland Edition"
        else: env_name = f"{env_name} Edition"
        self.title(f"LinuxTask v2.5.0 - {env_name}")
        self.geometry("420x50")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.recording = False
        self.playing = False
        self.events = []
        self.events_lock = threading.Lock()
        self.start_time = 0
        self.stop_threads = False
        self.loop_enabled = False
        self.humanize_enabled = ctk.BooleanVar(value=False)
        self.hotkey_rec = 66   # F8
        self.hotkey_play = 67  # F9
        self.is_mapping = None
        self.uinput_device = None
        self._rel_dirty = False
        self._processed_ids = set()
        self._processed_ids_lock = threading.Lock()
        self._input_devices = []
        self.start_cursor_pos = None
        self.init_uinput()

        self.grid_columnconfigure(list(range(7)), weight=1)
        self.grid_rowconfigure(0, weight=1)
        btn_opts = {
            "width": 40, "height": 40,
            "font": ("Noto Color Emoji", 16), "corner_radius": 5
        }

        # Define buttons in a list for DRY creation
        buttons_cfg = [
            ("📂", "#333333", "#444444", self.open_file),
            ("💾", "#333333", "#444444", self.save_file),
            ("⏺", "#d32f2f", "#b71c1c", self.toggle_record),
            ("⏵", "#388e3c", "#1b5e20", self.handle_play_key),
            ("🔁", "#333333", "#444444", self.toggle_loop)
        ]

        self.btns = []
        for i, (txt, fg, hov, cmd) in enumerate(buttons_cfg):
            btn = ctk.CTkButton(
                self, text=txt, fg_color=fg, hover_color=hov,
                command=cmd, **btn_opts
            )
            btn.grid(row=0, column=i, padx=2, pady=2)
            self.btns.append(btn)

        # Assign references to specific buttons we need to update late
        self.btn_rec = self.btns[2]
        self.btn_play = self.btns[3]
        self.btn_loop = self.btns[4]

        self.speed_var = ctk.StringVar(value="1x")
        self.speed_menu = ctk.CTkOptionMenu(
            self, values=["0.5x", "1x", "2x", "4x", "10x"],
            variable=self.speed_var, width=60, height=25, font=("Arial", 10)
        )
        self.speed_menu.grid(row=0, column=5, padx=2, pady=2)

        self.btn_settings = ctk.CTkButton(
            self, text="⚙", fg_color="transparent", hover_color="#222222",
            width=30, command=self.open_settings
        )
        self.btn_settings.grid(row=0, column=6, padx=2, pady=2)

        threading.Thread(
            target=self.global_hardware_listener, daemon=True
        ).start()

    def init_uinput(self):
        """Initializes a virtual UInput device for key replay."""
        try:
            keys = [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE] + list(range(1, 512))
            cap = {
                e.EV_KEY: keys,
                e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL]
            }
            self.uinput_device = evdev.UInput(
                cap, name="LinuxTask-Virtual", vendor=0x1234, product=0x5678
            )
            logger.info("UInput virtual device created successfully.")
        except PermissionError:
            logger.error(
                "Permission denied creating UInput device. "
                "Key replay will be disabled. Run install.sh to fix."
            )
            self.uinput_device = None
        except OSError as exc:
            logger.error("Failed to create UInput device: %s", exc)
            self.uinput_device = None

    def open_settings(self):
        """Opens the settings window."""
        if (hasattr(self, 'settings_win') and
                self.settings_win.winfo_exists()):
            self.settings_win.lift()
            return
        self.settings_win = ctk.CTkToplevel(self)
        self.settings_win.title("Settings")
        self.settings_win.geometry("300x250")
        self.settings_win.attributes("-topmost", True)
        self.settings_win.protocol("WM_DELETE_WINDOW", self._close_settings)
        self.settings_frame = ctk.CTkFrame(
            self.settings_win
        )
        self.settings_frame.pack(fill="both", expand=True)
        ctk.CTkLabel(
            self.settings_frame, text="Global Hotkeys",
            font=("Arial", 14, "bold")
        ).pack(pady=10)
        self.lbl_rec = ctk.CTkButton(
            self.settings_frame,
            text=f"Record: {self.get_key_name(self.hotkey_rec)}",
            command=lambda: self.start_mapping("rec", self.lbl_rec)
        )
        self.lbl_rec.pack(pady=5, fill="x", padx=20)
        self.lbl_play = ctk.CTkButton(
            self.settings_frame,
            text=f"Play/Stop: {self.get_key_name(self.hotkey_play)}",
            command=lambda: self.start_mapping("play", self.lbl_play)
        )
        self.lbl_play.pack(pady=5, fill="x", padx=20)
        ctk.CTkCheckBox(
            self.settings_frame, text="Humanize",
            variable=self.humanize_enabled
        ).pack(pady=10)

    def _close_settings(self):
        self.is_mapping = None
        self.settings_win.destroy()

    def start_mapping(self, mode, btn):
        """Starts hotkey mapping mode."""
        self.is_mapping = mode
        btn.configure(text="Press any key...", fg_color="#FFA500")

    def toggle_loop(self):
        """Toggles loop playback mode."""
        self.loop_enabled = not self.loop_enabled
        self.btn_loop.configure(
            text="🔁" if not self.loop_enabled else "🔂",
            fg_color="#1976d2" if self.loop_enabled else "#333333"
        )

    def get_input_devices(self):
        """Returns list of accessible input devices."""
        devices = []
        for path in evdev.list_devices():
            try:
                devices.append(evdev.InputDevice(path))
            except (PermissionError, OSError) as exc:
                logger.debug("Cannot open %s: %s", path, exc)
        return devices

    def global_hardware_listener(self):
        """Spawns a listener thread for each input device."""
        devices = self.get_input_devices()
        if not devices:
            logger.warning(
                "No input devices accessible. "
                "Global hotkeys and recording will not work."
            )
            return
        self._input_devices = devices
        logger.info("Listening on %d input devices.", len(devices))
        for d in devices:
            threading.Thread(
                target=self.device_loop, args=(d,), daemon=True
            ).start()

    def _event_id(self, event):
        return (event.sec, event.usec, event.type, event.code, event.value)

    def device_loop(self, dev):
        """Main event reading loop for a single input device."""
        try:
            for event in dev.read_loop():
                event_sec = event.sec
                event_usec = event.usec

                # Deduplicate events across multiple devices
                eid = (event_sec, event_usec, event.type, event.code, event.value)
                with self._processed_ids_lock:
                    if eid in self._processed_ids:
                        continue
                    self._processed_ids.add(eid)
                    # Cap set size to prevent memory leak during long sessions
                    if len(self._processed_ids) > 100000:
                        self._processed_ids.clear()

                # --- Mouse movement: record absolute or relative ---
                if event.type == e.EV_REL and self.recording:
                    if event.code == e.REL_WHEEL:
                        now = time.time() - self.start_time
                        direction = 'up' if event.value > 0 else 'down'
                        with self.events_lock:
                            self.events.append({
                                "type": "scroll",
                                "direction": direction,
                                "clicks": abs(event.value),
                                "time": now
                            })
                        continue
                    if event.code == e.REL_X:
                        self._rel_dx += event.value
                    elif event.code == e.REL_Y:
                        self._rel_dy += event.value
                    self._rel_dirty = True

                if event.type == e.EV_SYN and self.recording and self._rel_dirty:
                    self._rel_dirty = False
                    now = time.time() - self.start_time
                    if self.manager.supports_absolute_positioning:
                        pos = self.manager.get_cursor_pos()
                        with self.events_lock:
                            self.events.append({
                                "type": "pos", "x": pos[0],
                                "y": pos[1], "time": now
                            })
                    else:
                        with self.events_lock:
                            self.events.append({
                                "type": "rel", "dx": self._rel_dx,
                                "dy": self._rel_dy, "time": now
                            })
                    self._rel_dx = 0
                    self._rel_dy = 0

                # --- Key / button events ---
                if event.type == e.EV_KEY:
                    if self.is_mapping and event.value == 1:
                        if event.code == e.KEY_ESC:
                            logger.info("Hotkey mapping cancelled.")
                        else:
                            if self.is_mapping == "rec":
                                self.hotkey_rec = event.code
                            else:
                                self.hotkey_play = event.code
                            logger.info("Hotkey remapped to %s", self.get_key_name(event.code))

                        try:
                            if self.is_mapping == "rec":
                                self.lbl_rec.configure(text=f"Record: {self.get_key_name(self.hotkey_rec)}", fg_color=['#3B8ED0', '#1F6AA5'])
                            else:
                                self.lbl_play.configure(text=f"Play/Stop: {self.get_key_name(self.hotkey_play)}", fg_color=['#3B8ED0', '#1F6AA5'])
                        except Exception as exc:
                            logger.debug("Failed to update button text during mapping: %s", exc)

                        self.is_mapping = None
                        continue

                    if event.value == 1:
                        if event.code == self.hotkey_rec:
                            self.after(0, self.toggle_record)
                        elif event.code == self.hotkey_play:
                            self.after(0, self.handle_play_key)

                    with self.events_lock:
                        if self.recording and not self.stop_threads:
                            if event.code not in [
                                self.hotkey_rec, self.hotkey_play
                            ]:
                                self.events.append({
                                    "type": "key", "code": event.code,
                                    "val": event.value,
                                    "time": time.time() - self.start_time
                                })

        except OSError as exc:
            logger.warning(
                "Device '%s' disconnected or unavailable: %s",
                dev.name, exc
            )
        except Exception as exc:
            logger.error(
                "Unexpected error on device '%s': %s",
                dev.name, exc
            )

    def toggle_record(self):
        """Toggles recording state."""
        if self.playing:
            return
        if not self.recording:
            self.recording = True
            self._rel_dirty = False
            self._rel_dx = 0
            self._rel_dy = 0
            with self._processed_ids_lock:
                self._processed_ids.clear()
            with self.events_lock:
                self.events = []
            self.start_cursor_pos = self.manager.get_cursor_pos()
            self.start_time = time.time()
            self.btn_rec.configure(text="⏹", fg_color="#b71c1c")
            logger.info(
                "Recording started. Start pos: %s",
                self.start_cursor_pos
            )
        else:
            self.recording = False
            self.btn_rec.configure(text="⏺", fg_color="#d32f2f")
            with self.events_lock:
                ev_count = len(self.events)
            logger.info("Recording stopped. %d events captured.", ev_count)

    def handle_play_key(self):
        """Handles play/stop hotkey press."""
        if self.recording:
            return
        if self.playing:
            self.playing = False
        else:
            self.start_playback()

    def start_playback(self):
        """Starts playback in a background thread."""
        if self.playing:
            return
        with self.events_lock:
            if not self.events:
                return
        self.playing = True
        self.btn_play.configure(text="⏹", fg_color="#b71c1c")
        threading.Thread(target=self.playback_thread, daemon=True).start()

    def _apply_humanize(self, dx, dy, delay):
        """Applies jitter to movement and timing if humanize is enabled."""
        if not self.humanize_enabled.get():
            return dx, dy, delay
        jitter_x = random.randint(-2, 2)
        jitter_y = random.randint(-2, 2)
        time_variance = delay * random.uniform(0, 0.03)
        return dx + jitter_x, dy + jitter_y, delay + time_variance

    def playback_thread(self):
        """Main playback loop, runs in a background thread."""
        try:
            while self.playing:
                if self.start_cursor_pos is not None:
                    try:
                        self.manager.move_cursor(*self.start_cursor_pos)
                        time.sleep(0.01)
                    except Exception as exc:
                        logger.debug(
                            "Could not reset cursor position: %s", exc
                        )

                start_p = time.time()
                try:
                    speed = float(self.speed_var.get().replace("x", ""))
                except (ValueError, AttributeError):
                    speed = 1.0

                with self.events_lock:
                    events_copy = list(self.events)

                for i, ev in enumerate(events_copy):
                    if not self.playing:
                        break

                    target_time = start_p + (ev['time'] / speed)
                    remaining = target_time - time.time()
                    if remaining > 0:
                        threading.Event().wait(remaining)

                    if not self.playing:
                        break

                    if ev['type'] == "pos":
                        self.manager.move_cursor(ev['x'], ev['y'])

                    elif ev['type'] == "rel":
                        dx, dy = ev['dx'], ev['dy']
                        delay = 0
                        if self.humanize_enabled.get() and i + 1 < len(events_copy):
                            delay = (events_copy[i + 1]['time'] - ev['time']) / speed
                            dx, dy, delay = self._apply_humanize(dx, dy, delay)

                        handled = self.manager.move_relative(dx, dy)
                        if not handled and self.uinput_device is not None:
                            self.uinput_device.write(e.EV_REL, e.REL_X, dx)
                            self.uinput_device.write(e.EV_REL, e.REL_Y, dy)
                            self.uinput_device.syn()

                    elif ev['type'] == "scroll":
                        self.manager.scroll(
                            ev['direction'], ev.get('clicks', 1)
                        )

                    elif ev['type'] == "key":
                        if ev['code'] in [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE]:
                            handled = self.manager.mouse_button(ev['code'], ev['val'] == 1)
                            if handled:
                                continue

                        if self.uinput_device is not None:
                            self.uinput_device.write(
                                e.EV_KEY, ev['code'], ev['val']
                            )
                            self.uinput_device.syn()
                        else:
                            if ev['val'] == 1:
                                logger.warning(
                                    "UInput unavailable and driver could not handle "
                                    "mouse button (code=%d)", ev['code']
                                )

                if not self.loop_enabled:
                    break

        except Exception as exc:
            logger.error("Playback error: %s", exc)
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self.playing = False
            self.after(0, self._reset_play_button)

    def _reset_play_button(self):
        if not self.playing:
            self.btn_play.configure(
                text="⏵", fg_color="#388e3c"
            )

    def get_key_name(self, code):
        """Returns human-readable key name from evdev code."""
        name = evdev.ecodes.KEY.get(code, str(code))
        if isinstance(name, list):
            name = name[0]
        return name

    def save_file(self):
        """Saves recorded events to a JSON file."""
        f = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if f:
            try:
                with self.events_lock:
                    events_copy = list(self.events)
                macro_data = {
                    "start_pos": self.start_cursor_pos,
                    "events": events_copy
                }
                with open(f, 'w') as fp:
                    json.dump(macro_data, fp, indent=2)
                logger.info("Macro saved to %s (%d events).", os.path.basename(f), len(events_copy))
            except OSError as exc:
                logger.error("Failed to save file: %s", exc)

    def _validate_event(self, ev):
        if not isinstance(ev, dict):
            return False
        ev_type = ev.get("type")
        if ev_type == "pos":
            return isinstance(ev.get("x"), (int, float)) and isinstance(ev.get("y"), (int, float))
        elif ev_type == "rel":
            return isinstance(ev.get("dx"), (int, float)) and isinstance(ev.get("dy"), (int, float))
        elif ev_type == "scroll":
            return ev.get("direction") in ("up", "down") and isinstance(ev.get("clicks", 1), int)
        elif ev_type == "key":
            return isinstance(ev.get("code"), int) and isinstance(ev.get("val"), int)
        return False

    def open_file(self):
        """Loads recorded events from a JSON file."""
        f = filedialog.askopenfilename(
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if f:
            try:
                with open(f, 'r') as fp:
                    data = json.load(fp)
                if isinstance(data, dict):
                    raw_events = data.get("events", [])
                    pos = data.get("start_pos")
                    if pos and len(pos) == 2:
                        self.start_cursor_pos = tuple(pos)
                else:
                    raw_events = data
                    self.start_cursor_pos = None
                if not isinstance(raw_events, list):
                    raise ValueError("events must be a list")
                valid = [ev for ev in raw_events if self._validate_event(ev)]
                if len(valid) != len(raw_events):
                    logger.warning("Filtered %d invalid event(s) from macro.",
                                   len(raw_events) - len(valid))
                with self.events_lock:
                    self.events = valid
                logger.info(
                    "Macro loaded from %s (%d events, start_pos=%s).",
                    os.path.basename(f), len(valid), self.start_cursor_pos
                )
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                logger.error("Failed to load file: %s", exc)


if __name__ == "__main__":
    app = LinuxTaskApp()
    app.mainloop()
