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
    print("Error: Missing core dependencies (customtkinter or evdev).",
          file=sys.stderr)
    print("X11 users also need python-xlib; a missing per-environment "
          "dependency is reported with exact instructions by the "
          "driver factory.", file=sys.stderr)
    print("Please run install.sh or install them via pip: "
          "pip3 install --user customtkinter evdev python-xlib",
          file=sys.stderr)
    sys.exit(1)

import time
import random
import threading
import json
import os
import queue
import tkinter
import traceback
from collections import deque
from tkinter import filedialog
from drivers.factory import AutoDetectDriver

APP_VERSION = "3.0.2"

# Cap for the device_loop dedupe set: bounds memory in long sessions.
# When exceeded, only the oldest entries are evicted (see device_loop)
# instead of clearing the whole set, which would reopen double-fire.
MAX_DEDUPE_IDS = 100000
MAX_DEDUPE_EVICT = 10000

# Name of our own virtual replay device (see init_uinput). Listeners skip
# any device with this name so replayed events are not read back (echo).
VIRTUAL_DEVICE_NAME = "LinuxTask-Virtual"

CONFIG_DIR_NAME = "linuxtask"
CONFIG_FILE_NAME = "config.json"

# Shown ONCE per machine before the first recording ever starts.
PASSWORD_WARNING_TEXT = (
    "Recording captures EVERY key you press while it is on — "
    "including usernames, passwords, credit-card numbers, and "
    "private messages typed in any window.\n\n"
    "Do not type sensitive information while the red (■) "
    "indicator is showing. Stop recording (F8) before logging in "
    "anywhere."
)
RECORDING_TOOLTIP_TEXT = (
    "RECORDING - every key, including passwords, is being captured."
)


class ToolTip:
    """Minimal hover tooltip (customtkinter has no built-in one).

    Shows a small top-level label while the mouse hovers the widget.
    Used so emoji-only toolbar buttons stay understandable when the
    emoji font is missing (issue #3).
    """

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event=None):
        if self.tip is not None:
            return
        try:
            x = self.widget.winfo_rootx() + 10
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            self.tip = tip = tkinter.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            label = tkinter.Label(
                tip, text=self.text, background="#222222",
                foreground="white", relief="solid", borderwidth=1,
                font=("Arial", 9), padx=6, pady=2,
            )
            label.pack()
        except Exception:
            logger.debug("Failed to show tooltip.", exc_info=True)
            self.tip = None

    def _hide(self, _event=None):
        try:
            if self.tip is not None:
                self.tip.destroy()
        except Exception:
            logger.debug("Failed to hide tooltip.", exc_info=True)
        finally:
            self.tip = None


class LinuxTaskApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        try:
            self.manager = AutoDetectDriver()
        except RuntimeError as exc:
            # Missing system deps (e.g. python3-dbus on KDE Wayland) or an
            # unsupported desktop. Show a visible dialog, not a traceback.
            logger.error("Driver initialization failed: %s", exc)
            try:
                import tkinter.messagebox as mb
                mb.showerror("LinuxTask - Initialization failed", str(exc))
            except Exception:
                logger.debug("Failed to show error dialog.", exc_info=True)
            sys.exit(1)
        env_name = self.manager.__class__.__name__.replace("Driver", "")
        if env_name == "X11": env_name = "X11 Edition"
        elif env_name == "Gnome": env_name = "GNOME Edition"
        elif env_name == "KdeWayland": env_name = "KDE Wayland Edition"
        elif env_name == "Hyprland": env_name = "Hyprland Edition"
        else: env_name = f"{env_name} Edition"
        self.title(f"LinuxTask v{APP_VERSION} - {env_name}")
        # Compact toolbar (TinyTask-inspired): 400x44 instead of 420x50.
        self.geometry("400x44")
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
        # Pending relative-motion accumulators. Written from evdev listener
        # threads and reset in toggle_record(); initialized here so no code
        # path depends on toggle_record() having run first.
        self._rel_dx = 0
        self._rel_dy = 0
        self._rel_dirty = False
        self._processed_ids = set()
        self._processed_ids_lock = threading.Lock()
        # Insertion order of _processed_ids, for oldest-first eviction.
        self._processed_ids_order = deque()
        self._input_devices = []
        # Thread-safe queue: evdev listener threads push "rec" / "play" /
        # "play_finished" actions here; the UI thread consumes them via
        # _poll_hotkeys(). Never call tkinter methods (after/configure)
        # directly from listener/playback threads.
        self._ui_queue = queue.Queue()
        self.app_config = self._load_app_config()
        self.start_cursor_pos = None
        self.init_uinput()

        self.grid_columnconfigure(list(range(7)), weight=1)
        self.grid_rowconfigure(0, weight=1)
        btn_opts = {
            "width": 32, "height": 32,
            # NOTE: must be a monochrome outline font. Tk cannot render
            # color-bitmap emoji (e.g. Noto Color Emoji) -- buttons show
            # up as pixelated tofu boxes. All glyphs below are covered
            # by DejaVu Sans, which ships with virtually every distro.
            "font": ("DejaVu Sans", 14), "corner_radius": 5
        }

        # Define buttons in a list for DRY creation
        # (text, tooltip, fg, hover, command)
        buttons_cfg = [
            ("Open", "Open macro", "#333333", "#444444", self.open_file),
            ("Save", "Save macro", "#333333", "#444444", self.save_file),
            ("●", "Record (F8)", "#d32f2f", "#b71c1c", self.toggle_record),
            ("▶", "Play / Stop (F9)", "#388e3c", "#1b5e20", self.handle_play_key),
            ("↻", "Loop playback", "#333333", "#444444", self.toggle_loop)
        ]

        self.btns = []
        for i, (txt, tip, fg, hov, cmd) in enumerate(buttons_cfg):
            btn = ctk.CTkButton(
                self, text=txt, fg_color=fg, hover_color=hov,
                command=cmd, **btn_opts
            )
            btn.grid(row=0, column=i, padx=2, pady=2)
            ToolTip(btn, tip)
            self.btns.append(btn)

        # Assign references to specific buttons we need to update late
        self.btn_rec = self.btns[2]
        self.btn_play = self.btns[3]
        self.btn_loop = self.btns[4]
        # Text labels need a smaller font to fit the 32px buttons.
        self.btns[0].configure(font=("DejaVu Sans", 10))
        self.btns[1].configure(font=("DejaVu Sans", 10))

        self.speed_var = ctk.StringVar(value="1x")
        self.speed_menu = ctk.CTkOptionMenu(
            self, values=["0.5x", "1x", "2x", "4x", "10x"],
            variable=self.speed_var, width=56, height=24, font=("Arial", 10)
        )
        self.speed_menu.grid(row=0, column=5, padx=2, pady=2)

        self.btn_settings = ctk.CTkButton(
            self, text="⚙", fg_color="transparent", hover_color="#222222",
            width=26, font=("DejaVu Sans", 14), command=self.open_settings
        )
        self.btn_settings.grid(row=0, column=6, padx=2, pady=2)
        ToolTip(self.btn_settings, "Settings")
        ToolTip(self.speed_menu, "Playback speed")

        self.after(50, self._poll_hotkeys)
        threading.Thread(
            target=self.global_hardware_listener, daemon=True
        ).start()

    def _poll_hotkeys(self):
        """Runs on the UI thread: consumes actions queued by workers."""
        try:
            while True:
                action = self._ui_queue.get_nowait()
                if action == "rec":
                    self.toggle_record()
                elif action == "play":
                    self.handle_play_key()
                elif action == "play_finished":
                    self.btn_play.configure(text="▶", fg_color="#388e3c")
                elif action == "no_devices":
                    try:
                        import tkinter.messagebox as mb
                        mb.showwarning(
                            "LinuxTask - No input devices",
                            "No readable input devices found.\n\n"
                            "Global hotkeys (F8/F9) and recording will not work.\n\n"
                            "Fix: run ./tools/install.sh, confirm you are in the "
                            "'input' group (groups $USER), then log out and back in.")
                    except Exception:
                        logger.debug("Failed to show warning dialog.", exc_info=True)
        except queue.Empty:
            pass
        finally:
            try:
                self.after(50, self._poll_hotkeys)
            except Exception:
                logger.debug("Hotkey poll reschedule failed.", exc_info=True)

    def init_uinput(self):
        """Initializes a virtual UInput device for key replay."""
        try:
            keys = [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE] + list(range(1, 512))
            cap = {
                e.EV_KEY: keys,
                e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL]
            }
            self.uinput_device = evdev.UInput(
                cap, name=VIRTUAL_DEVICE_NAME, vendor=0x1234, product=0x5678
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
            # Loop state is shown by color (blue = on), so one glyph suffices.
            text="↻",
            fg_color="#1976d2" if self.loop_enabled else "#333333"
        )

    def get_input_devices(self):
        """Returns list of accessible input devices."""
        # NOTE: python-evdev >= 2.0 only lists readable+WRITABLE devices
        # by default, but our udev rule grants event* READ-ONLY on purpose
        # (recording only listens). Ask for readable devices explicitly;
        # fall back to the old no-arg call on evdev 1.x.
        try:
            paths = evdev.list_devices(writable=False)
        except TypeError:
            paths = evdev.list_devices()
        # NOTE: __dict__ lookup (not getattr): same reason as in
        # device_loop — on instances built via __new__ (unit tests, no
        # display) getattr() on a missing attr raises RecursionError
        # instead of returning the default. Verified empirically.
        own = self.__dict__.get("uinput_device")
        own_name = None
        if own is not None:
            try:
                own_name = own.name
            except (OSError, AttributeError):
                own_name = None
        devices = []
        for path in paths:
            try:
                dev = evdev.InputDevice(path)
            except (PermissionError, OSError) as exc:
                logger.debug("Cannot open %s: %s", path, exc)
                continue
            # Skip our own virtual replay device: playback writes key and
            # mouse events through it, and without this filter the listener
            # threads would read those replayed events back (echo),
            # re-triggering the F8/F9 hotkeys mid-playback. The match is by
            # device NAME, so a second app instance would also ignore the
            # first one's virtual device — acceptable, since each instance
            # only replays through its own UInput.
            try:
                dev_name = dev.name
            except (OSError, AttributeError):
                dev_name = None
            if (own_name is not None and dev_name is not None
                    and dev_name == own_name == VIRTUAL_DEVICE_NAME):
                logger.debug(
                    "Skipping own virtual device '%s' (%s).", dev_name, path
                )
                continue
            devices.append(dev)
        return devices

    def global_hardware_listener(self):
        """Spawns a listener thread for each input device."""
        devices = self.get_input_devices()
        if not devices:
            logger.warning(
                "No input devices accessible. "
                "Global hotkeys and recording will not work. "
                "Fix: re-run ./tools/install.sh, check membership in "
                "the 'input' group (groups $USER), then log out and back in."
            )
            self._ui_queue.put("no_devices")
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
                # Deduplicate events across multiple devices
                eid = self._event_id(event)
                with self._processed_ids_lock:
                    if eid in self._processed_ids:
                        continue
                    self._processed_ids.add(eid)
                    # NOTE: __dict__ lookup (not getattr): this class is a
                    # tkinter widget whose __getattr__ recurses on missing
                    # attrs for instances built via __new__ in tests.
                    order = self.__dict__.get("_processed_ids_order")
                    if order is not None:
                        order.append(eid)
                    # Cap set size to prevent memory leak during long sessions.
                    # Evict only the oldest IDs so recent events stay
                    # deduplicated (a full clear would reopen double-fire).
                    if len(self._processed_ids) > MAX_DEDUPE_IDS:
                        if order is not None:
                            for _ in range(min(len(order), MAX_DEDUPE_EVICT)):
                                self._processed_ids.discard(order.popleft())
                                if len(self._processed_ids) <= MAX_DEDUPE_IDS - MAX_DEDUPE_EVICT:
                                    break
                        else:
                            self._processed_ids.clear()

                # --- Mouse movement: record absolute or relative ---
                if event.type == e.EV_REL and self.recording:
                    if event.code == e.REL_WHEEL:
                        # monotonic: immune to NTP adjustments/DST jumps.
                        now = time.monotonic() - self.start_time
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
                        with self.events_lock:
                            self._rel_dx += event.value
                            self._rel_dirty = True
                    elif event.code == e.REL_Y:
                        with self.events_lock:
                            self._rel_dy += event.value
                            self._rel_dirty = True
                    else:
                        with self.events_lock:
                            self._rel_dirty = True

                if event.type == e.EV_SYN and self.recording:
                    with self.events_lock:
                        rel_dx, rel_dy = self._rel_dx, self._rel_dy
                        rel_dirty = self._rel_dirty
                        self._rel_dirty = False
                        self._rel_dx = 0
                        self._rel_dy = 0
                    if rel_dirty:
                        now = time.monotonic() - self.start_time
                        if self.manager.supports_absolute_positioning:
                            pos = self.manager.get_cursor_pos()
                            if pos is None:
                                logger.debug("EV_SYN flush skipped: cursor pos unknown")
                            else:
                                with self.events_lock:
                                    self.events.append({
                                        "type": "pos", "x": pos[0],
                                        "y": pos[1], "time": now
                                    })
                        else:
                            with self.events_lock:
                                self.events.append({
                                    "type": "rel", "dx": rel_dx,
                                    "dy": rel_dy, "time": now
                                })

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

                    # Global hotkeys (on key press only).
                    # NOTE: never touch tkinter here — this runs on an evdev
                    # listener thread. Push to the queue; UI polls it.
                    if event.value == 1:
                        if event.code == self.hotkey_rec:
                            self._ui_queue.put("rec")
                        elif event.code == self.hotkey_play:
                            self._ui_queue.put("play")

                    with self.events_lock:
                        if self.recording:
                            if event.code not in [
                                self.hotkey_rec, self.hotkey_play
                            ]:
                                self.events.append({
                                    "type": "key", "code": event.code,
                                    "val": event.value,
                                    "time": time.monotonic() - self.start_time
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

    def _config_path(self):
        """Path of the persistent app config file.

        Respects XDG_CONFIG_HOME, defaulting to ~/.config.
        """
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
            os.path.expanduser("~"), ".config"
        )
        return os.path.join(base, CONFIG_DIR_NAME, CONFIG_FILE_NAME)

    def _load_app_config(self):
        """Read the persistent config; return {} on any problem."""
        try:
            with open(self._config_path(), "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            return cfg if isinstance(cfg, dict) else {}
        except (OSError, ValueError) as exc:
            logger.debug("No usable app config yet (%s).", exc)
            return {}

    def _save_app_config(self):
        """Persist app_config; warn only (never break the app)."""
        try:
            path = self._config_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self.app_config, fh)
        except OSError as exc:
            logger.warning("Could not save app config: %s", exc)

    def _confirm_password_warning(self):
        """First-recording warning. Returns True when recording may start.

        Runs on the UI thread (toolbar button or _poll_hotkeys), so the
        evdev listener threads keep running and no input event is lost --
        recording simply has not started yet. Cancel (or closing the
        window) returns False and recording never starts.
        """
        # Re-entrancy guard: wait_window() below runs a nested event loop
        # in which _poll_hotkeys keeps firing, so a queued "rec" could
        # call this again and open a second dialog. __dict__ lookup (not
        # getattr): bare test instances built via __new__ have no attrs,
        # and getattr() on a missing attr raises RecursionError here.
        if self.__dict__.get("_warning_open"):
            return False
        self.__dict__["_warning_open"] = True
        try:
            dlg = tkinter.Toplevel(self)
            dlg.title("LinuxTask - Sensitive input")
            dlg.attributes("-topmost", True)
            dlg.transient(self)
            dlg.resizable(False, False)
            outcome = {"proceed": False, "hide": False}
            hide_var = tkinter.BooleanVar(value=False)

            ctk.CTkLabel(
                dlg, text=PASSWORD_WARNING_TEXT, wraplength=320,
                font=("Arial", 12),
            ).pack(padx=16, pady=(16, 8))
            ctk.CTkCheckBox(
                dlg, text="Don't show again", variable=hide_var,
            ).pack(padx=16, pady=4, anchor="w")

            row = ctk.CTkFrame(dlg, fg_color="transparent")
            row.pack(padx=16, pady=(8, 16), fill="x")

            def _ok():
                outcome["proceed"] = True
                outcome["hide"] = bool(hide_var.get())
                dlg.destroy()

            def _cancel():
                dlg.destroy()

            ctk.CTkButton(row, text="Cancel", command=_cancel).pack(
                side="left", expand=True, padx=(0, 4))
            ctk.CTkButton(row, text="Start recording", command=_ok).pack(
                side="left", expand=True, padx=(4, 0))
            dlg.protocol("WM_DELETE_WINDOW", _cancel)
            try:
                # Visible before grabbing so the window manager can
                # focus it; if the grab fails the dialog still works.
                dlg.wait_visibility()
                dlg.grab_set()
            except tkinter.TclError:
                logger.debug(
                    "Dialog grab failed; continuing without grab."
                )
            self.wait_window(dlg)

            if outcome["hide"]:
                cfg = self.__dict__.get("app_config")
                if cfg is None:
                    cfg = self.app_config = {}
                cfg["hide_password_warning"] = True
                self._save_app_config()
            # A hotkey pressed while the dialog was open must not fire
            # right after it closes (double-toggle).
            self._drain_hotkey_actions()
            return outcome["proceed"]
        finally:
            self.__dict__["_warning_open"] = False

    def _drain_hotkey_actions(self):
        """Drop stale queued hotkey actions (they went obsolete)."""
        try:
            while True:
                self._hotkey_actions.get_nowait()
        except queue.Empty:
            pass

    def toggle_record(self):
        """Toggles recording state."""
        if self.playing:
            return
        if not self.recording:
            # NOTE: __dict__ lookups (not getattr): bare test instances
            # built via __new__ have no app_config attr, and getattr()
            # on a missing attr raises RecursionError here.
            cfg = self.__dict__.get("app_config") or {}
            if (not cfg.get("hide_password_warning")
                    and not self._confirm_password_warning()):
                return  # Cancelled (or dialog already open): don't record.
            self.recording = True
            with self.events_lock:
                self._rel_dirty = False
                self._rel_dx = 0
                self._rel_dy = 0
            with self._processed_ids_lock:
                self._processed_ids.clear()
                # __dict__ lookup: see note in device_loop.
                order = self.__dict__.get("_processed_ids_order")
                if order is not None:
                    order.clear()
            with self.events_lock:
                self.events = []
            self.start_cursor_pos = self.manager.get_cursor_pos()
            # monotonic: event timestamps below are deltas from this base,
            # so a clock jump mid-recording must not skew them.
            self.start_time = time.monotonic()
            self.rec_tip = ToolTip(
                self.btn_rec, RECORDING_TOOLTIP_TEXT)
            self.btn_rec.configure(text="■", fg_color="#b71c1c")
            logger.info(
                "Recording started. Start pos: %s",
                self.start_cursor_pos
            )
        else:
            self.recording = False
            self.rec_tip = ToolTip(self.btn_rec, "Record (F8)")
            self.btn_rec.configure(text="●", fg_color="#d32f2f")
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
                logger.warning("Play pressed with no events recorded.")
                return
        self.playing = True
        self.btn_play.configure(text="■", fg_color="#b71c1c")
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
        # Tally for the end-of-playback summary. Reset here (not in
        # start_playback) so it is always owned by the running thread.
        attempted_events = 0
        failed_events = 0
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

                start_p = time.monotonic()
                try:
                    speed = float(self.speed_var.get().replace("x", ""))
                except (ValueError, AttributeError):
                    speed = 1.0

                with self.events_lock:
                    events_copy = list(self.events)
                logger.info(
                    "Playback started: %d events at %sx.",
                    len(events_copy), speed,
                )
                # Let the driver re-sync its tracked position once
                # (drivers that need it implement sync_for_playback).
                sync = getattr(self.manager, "sync_for_playback", None)
                if callable(sync):
                    try:
                        sync()
                    except Exception as exc:
                        logger.debug("sync_for_playback failed: %s", exc)

                for i, ev in enumerate(events_copy):
                    if not self.playing:
                        break

                    # One bad event must not abort the whole macro: the timing
                    # math reads ev['time'] too, so it belongs inside this try.
                    attempted_events += 1
                    try:
                        target_time = start_p + (ev['time'] / speed)
                        remaining = target_time - time.monotonic()
                        if remaining > 0:
                            # Sliced wait: Stop/F9 takes effect promptly
                            # instead of only after the full gap elapses.
                            deadline = time.monotonic() + remaining
                            while self.playing:
                                left = deadline - time.monotonic()
                                if left <= 0:
                                    break
                                time.sleep(min(left, 0.05))

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
                            elif not handled:
                                logger.warning(
                                    "Relative move (%d, %d) dropped: driver "
                                    "declined and UInput unavailable.", dx, dy
                                )

                        elif ev['type'] == "scroll":
                            handled = self.manager.scroll(
                                ev['direction'], ev.get('clicks', 1)
                            )
                            if not handled:
                                if self.uinput_device is not None:
                                    wheel = 1 if ev['direction'] == 'up' else -1
                                    for _ in range(ev.get('clicks', 1)):
                                        self.uinput_device.write(
                                            e.EV_REL, e.REL_WHEEL, wheel
                                        )
                                    self.uinput_device.syn()
                                else:
                                    logger.warning(
                                        "Scroll (%s x%d) dropped: driver "
                                        "declined and UInput unavailable.",
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
                    except Exception as exc:
                        failed_events += 1
                        logger.warning(
                            "Playback event %d (%s) failed, skipping: %s",
                            i, ev.get('type'), exc, exc_info=True
                        )
                        continue

                if not self.loop_enabled:
                    break

            if failed_events > 0:
                logger.warning(
                    "Playback finished with %d failed events out of %d.",
                    failed_events, attempted_events
                )

        except Exception as exc:
            logger.error("Playback error: %s", exc)
            logger.error(traceback.format_exc())
        finally:
            self.playing = False
            # UI reset via queue (this runs on a worker thread).
            self._ui_queue.put("play_finished")

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
                with open(f, 'w', encoding="utf-8") as fp:
                    json.dump(macro_data, fp, indent=2)
                logger.info("Macro saved to %s (%d events).", os.path.basename(f), len(events_copy))
            except OSError as exc:
                logger.error("Failed to save file: %s", exc)

    def _validate_event(self, ev):
        if not isinstance(ev, dict):
            return False
        # playback_thread reads ev['time'] for every event (src/main.py:581)
        # before dispatching it, so a non-numeric 'time' there aborts the whole
        # macro. A missing 'time' stays valid (legacy macros omit it) but is
        # caught per-event by the try in playback_thread; only reject a
        # 'time' that is present and not a real number.
        if "time" in ev and (not isinstance(ev["time"], (int, float))
                             or isinstance(ev["time"], bool)):
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
                with open(f, 'r', encoding="utf-8") as fp:
                    data = json.load(fp)
                if isinstance(data, dict):
                    raw_events = data.get("events", [])
                    pos = data.get("start_pos")
                    if (isinstance(pos, (list, tuple)) and len(pos) == 2
                            and all(isinstance(v, (int, float))
                                    and not isinstance(v, bool) for v in pos)):
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


def main():
    """Entry point (also used by the AppImage console script)."""
    app = LinuxTaskApp()
    app.mainloop()


if __name__ == "__main__":
    main()
