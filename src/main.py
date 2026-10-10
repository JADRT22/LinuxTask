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
import threading
import json
import os
import queue
import tkinter
from collections import deque
# filedialog must stay bound in this module: tests patch('main.filedialog...').
from tkinter import filedialog
from drivers.factory import AutoDetectDriver
# Capture/playback live in their own modules and are mixed in below, so the
# public surface (LinuxTaskApp.<method>) is unchanged for callers and tests.
from recorder import Recorder, VIRTUAL_DEVICE_NAME
from playback import Playback

APP_VERSION = "3.2.0"

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


class LinuxTaskApp(ctk.CTk, Recorder, Playback):
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
        elif env_name == "Sway": env_name = "Sway Edition"
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
        # KDE portal driver reports skipped input through warn_fn; push it
        # on the same worker-safe queue (_poll_hotkeys shows it once).
        if hasattr(self.manager, "warn_fn"):
            self.manager.warn_fn = (
                lambda _msg: self._ui_queue.put("driver_warning"))
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
                elif action == "driver_warning":
                    if not self.__dict__.get("_driver_warning_shown"):
                        self.__dict__["_driver_warning_shown"] = True
                        try:
                            import tkinter.messagebox as mb
                            mb.showwarning(
                                "LinuxTask - Driver warning",
                                "The desktop driver could not replay part of "
                                "the macro (portal not ready or the call "
                                "failed).\n\nInput fell back to the virtual "
                                "uinput device when possible, otherwise it "
                                "was skipped.\n\nOn KDE Wayland, approve the "
                                "portal dialog on first run. Details are in "
                                "the log.")
                        except Exception:
                            logger.debug(
                                "Failed to show driver warning dialog.",
                                exc_info=True)
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
                self._ui_queue.get_nowait()
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

    def get_key_name(self, code):
        """Returns human-readable key name from evdev code."""
        name = evdev.ecodes.KEY.get(code, str(code))
        if isinstance(name, list):
            name = name[0]
        return name


def main():
    """Entry point (also used by the AppImage console script)."""
    app = LinuxTaskApp()
    app.mainloop()


if __name__ == "__main__":
    main()
