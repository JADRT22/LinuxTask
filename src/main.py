# -*- coding: utf-8 -*-
"""
LinuxTask - main.py
Description: Main application loop and UI.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import logging
import sys

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

import json
import os
import queue
import threading
import time
import tkinter
from collections import deque

# filedialog must stay bound in this module: tests patch('main.filedialog...'),
# and the read-only AppImage path calls it for "Save to…".
from tkinter import filedialog

import ui_theme
import updater
from drivers.factory import AutoDetectDriver
from playback import Playback

# Capture/playback live in their own modules and are mixed in below, so the
# public surface (LinuxTaskApp.<method>) is unchanged for callers and tests.
from recorder import VIRTUAL_DEVICE_NAME, Recorder
from ui_widgets import AdwButton, AdwMenu, AdwProgress, AdwRow, AdwSwitch

APP_VERSION = "3.7.0"

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

# Chrome for the dark UI, which is the only mode the app has. Every value
# comes from ui_theme, which carries the libadwaita token it was extracted
# from -- nothing down here invents a colour. The names survive because
# recorder.py, playback.py and the tests refer to them.
UI = ui_theme.default_palette()
UI_WINDOW_BG = UI.window_bg
UI_NEUTRAL = None               # Adwaita flat buttons: no fill until hover
UI_NEUTRAL_HOVER = UI.hover
UI_NEUTRAL_BORDER = UI.border
UI_DROPDOWN_BG = UI.popover_bg
RECORDING_FILL = UI.destructive   # red_4: the record button, armed or not
PLAYING_IDLE_FILL = UI.success    # green_5: ready to replay
PLAYING_FILL = UI.destructive      # stop is the destructive action
LOOP_FILL = UI.accent              # the desktop accent while looping
MAPPING_FILL = UI.warning          # waiting for a key press

# Logical size of the toolbar. The window is that multiplied by the display
# scale, and every widget metric goes through the same factor, so the row
# holds together on a HiDPI screen instead of keeping 400x44 physical pixels.
UI_WIDTH = 400
UI_HEIGHT = 44
UI_SCALE = 1.0


def px(value):
    """A logical pixel value in physical pixels, for the current scale."""
    return int(round(value * UI_SCALE))


def set_ui_scale(scale):
    """Sets the logical-to-physical factor the toolbar is built with.

    Must be called before the window is constructed: every widget metric,
    padding and the window geometry read UI_SCALE at build time. The
    capture harness uses it to render the same toolbar at 1x and 2x, which
    is how the HiDPI render is produced without a second code path.
    """
    global UI_SCALE
    UI_SCALE = float(scale)
    return UI_SCALE


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
                tip, text=self.text, background=UI.popover_bg,
                foreground=UI.window_fg, relief="solid", borderwidth=1,
                font=("DejaVu Sans", 9), padx=6, pady=2,
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
    # Window-title label per driver class name ("GnomeDriver" -> "GNOME").
    EDITION_NAMES = {
        "X11": "X11",
        "Gnome": "GNOME",
        "KdeWayland": "KDE Wayland",
        "Hyprland": "Hyprland",
        "Sway": "Sway",
    }

    def __init__(self):
        super().__init__()
        # A RuntimeError here (missing system deps such as python3-dbus on
        # KDE Wayland, or an unsupported desktop) is main()'s to report:
        # sys.exit() from a constructor leaves a half-built Tk root behind
        # and gives the caller no way to recover.
        self.manager = AutoDetectDriver()
        env_name = self.EDITION_NAMES.get(
            self.manager.__class__.__name__.replace("Driver", ""),
            self.manager.__class__.__name__.replace("Driver", ""))
        self.title(f"LinuxTask v{APP_VERSION} - {env_name} Edition")
        # Compact toolbar: 400x44 logical pixels, scaled by the display's
        # factor so a HiDPI screen gets 800x88 of real pixels instead of a
        # 400x44 window with oversized fonts inside it.
        self.geometry("%dx%d" % (UI_WIDTH * UI_SCALE,
                                 UI_HEIGHT * UI_SCALE))
        self.attributes("-topmost", True)
        self.resizable(False, False)
        # One flat base for every surface, taken from the Adwaita dark
        # window token rather than CTk's default gray14.
        self.configure(fg_color=UI_WINDOW_BG)
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
        # KDE portal driver reports skipped input through warn_fn; the
        # GNOME driver warns when the cursor bridge is absent so the
        # delta fallback is expected. The callback stores the actual
        # message on the manager (thread-safe simple attribute write)
        # and pushes the same worker-safe queue token; _poll_hotkeys
        # shows the driver's own text instead of a desktop-specific
        # hard-coded one.
        if hasattr(self.manager, "warn_fn"):
            self.manager.warn_fn = self._driver_warn_fn
        self.app_config = self._load_app_config()
        self.start_cursor_pos = None
        self.init_uinput()
        # AppImage update state. Written by workers as plain attributes and
        # consumed on the UI thread (see _handle_update_*); the feature is
        # absent entirely when updater.appimage_path() is None.
        self._update_info = None
        self._update_status = ""
        self._update_error = None
        self._update_target = None
        self._update_progress = (0, 0)
        self._update_last_percent = -1
        self._update_check_running = False
        self._update_manual = False
        self._update_available = False
        self._update_downloading = False
        self._update_installed = False
        self.after(200, self._start_update_check)

        self.grid_columnconfigure(list(range(7)), weight=1)
        self.grid_rowconfigure(0, weight=1)
        btn_opts = {
            "width": 32, "height": 32,
            # NOTE: must be a monochrome outline font. Tk cannot render
            # color-bitmap emoji (e.g. Noto Color Emoji) -- buttons show
            # up as pixelated tofu boxes. All glyphs below are covered
            # by DejaVu Sans, which ships with virtually every distro.
            "font": ("DejaVu Sans", 14), "corner_radius": 6,
            # Discreet 1px outline on every toolbar button (Adwaita style),
            # including the red/green state buttons.
            "border_width": 1, "border_color": UI_NEUTRAL_BORDER
        }

        # Define buttons in a list for DRY creation
        # (text, tooltip, fg, hover, command)
        buttons_cfg = [
            ("Open", "Open macro", UI_NEUTRAL, UI_NEUTRAL_HOVER, self.open_file),
            ("Save", "Save macro", UI_NEUTRAL, UI_NEUTRAL_HOVER, self.save_file),
            ("●", "Record (F8)", RECORDING_FILL, None, self.toggle_record),
            ("▶", "Play / Stop (F9)", PLAYING_IDLE_FILL, None, self.handle_play_key),
            ("↻", "Loop playback", UI_NEUTRAL, UI_NEUTRAL_HOVER, self.toggle_loop)
        ]

        self.btns = []
        for i, (txt, tip, fg, hov, cmd) in enumerate(buttons_cfg):
            btn = AdwButton(
                self, text=txt, fg_color=fg, hover_color=hov,
                command=cmd, scale=UI_SCALE, palette=UI,
                raised=(i < 2), **btn_opts
            )
            btn.grid(row=0, column=i, padx=int(2 * UI_SCALE),
                     pady=int(2 * UI_SCALE))
            ToolTip(btn, tip)
            self.btns.append(btn)

        # Assign references to specific buttons we need to update late
        self.btn_rec = self.btns[2]
        self.btn_play = self.btns[3]
        self.btn_loop = self.btns[4]
        # "Open"/"Save" are wider than the 32px icon buttons (DejaVu Sans 10
        # measures "Open" at 34px), so these two get width=40 to keep the
        # label fully inside the 1px outline instead of touching it.
        self.btns[0].configure(font=("DejaVu Sans", 10), width=40)
        self.btns[1].configure(font=("DejaVu Sans", 10), width=40)

        self.speed_var = ctk.StringVar(value="1x")
        # Adwaita dropdown: a raised chevron button that opens a popover of
        # the five speeds. Same StringVar and the same trace as before, so
        # playback keeps reading the value it always read.
        self.speed_menu = AdwMenu(
            self, values=["0.5x", "1x", "2x", "4x", "10x"],
            variable=self.speed_var, width=56, height=28,
            scale=UI_SCALE, palette=UI,
        )
        self.speed_menu.grid(row=0, column=5, padx=int(2 * UI_SCALE),
                            pady=int(2 * UI_SCALE))
        self._bind_playback_settings()

        self.btn_settings = AdwButton(
            self, text="⚙", fg_color=None,
            hover_color=UI_NEUTRAL_HOVER, raised=False,
            width=26, height=28, font=("DejaVu Sans", 14),
            scale=UI_SCALE, palette=UI, command=self.open_settings
        )
        self.btn_settings.grid(row=0, column=6, padx=int(2 * UI_SCALE),
                              pady=int(2 * UI_SCALE))
        ToolTip(self.btn_settings, "Settings")
        ToolTip(self.speed_menu, "Playback speed")

        self.after(50, self._poll_hotkeys)
        threading.Thread(
            target=self.global_hardware_listener, daemon=True
        ).start()

    def _driver_warn_fn(self, msg):
        """Runs on driver threads: stores the real warning text and queues
        the one-time UI notice for _poll_hotkeys."""
        self.manager.driver_warning_detail = msg
        self._ui_queue.put("driver_warning")

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
                    self.btn_play.configure(text="▶", fg_color=PLAYING_IDLE_FILL)
                elif action == "update_checked":
                    self._handle_update_checked()
                elif action == "update_progress":
                    self._handle_update_progress()
                elif action == "update_installed":
                    self._handle_update_installed()
                elif action == "update_failed":
                    self._handle_update_failed()
                elif action == "driver_warning":
                    if not self.__dict__.get("_driver_warning_shown"):
                        self.__dict__["_driver_warning_shown"] = True
                        try:
                            import tkinter.messagebox as mb
                            detail = getattr(
                                self.manager, "driver_warning_detail", None)
                            if detail:
                                message = (
                                    "The desktop driver reported a "
                                    "problem:\n\n" + detail +
                                    "\n\nDetails are in the log.")
                            else:
                                message = (
                                    "The desktop driver could not replay "
                                    "part of the macro (portal not ready "
                                    "or the call failed).\n\nInput fell "
                                    "back to the virtual uinput device "
                                    "when possible, otherwise it was "
                                    "skipped.\n\nOn KDE Wayland, approve "
                                    "the portal dialog on first run. "
                                    "Details are in the log.")
                            mb.showwarning(
                                "LinuxTask - Driver warning", message)
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
        # Width fixed, height left to the window manager: the window then grows
        # to whatever the rows ask for, at any scale. Sizing it by hand meant
        # measuring the packed content before the canvas rows had drawn, which
        # clipped the last row at 2x (232 was right at 1x and too short there).
        self.settings_win.minsize(px(300), px(120))
        self.settings_win.attributes("-topmost", True)
        # Flat window colour, no card: the same surface the toolbar sits on,
        # like a libadwaita preferences page.
        self.settings_win.configure(fg_color=UI_WINDOW_BG)
        self.settings_win.protocol("WM_DELETE_WINDOW", self._close_settings)
        self.settings_frame = tkinter.Frame(
            self.settings_win, bg=UI_WINDOW_BG
        )
        self.settings_frame.pack(fill="both", expand=True)
        self._section_title("Global Hotkeys", padx=px(18), pady=(px(16), px(2)))
        tkinter.Label(
            self.settings_frame,
            text="Click a shortcut, then press the new key.",
            bg=UI_WINDOW_BG, fg=UI.dim, anchor="w",
            font=("DejaVu Sans", int(round(9 * UI_SCALE))),
        ).pack(fill="x", padx=px(18), pady=(0, px(10)))
        self.lbl_rec = AdwRow(
            self.settings_frame,
            text=f"Record: {self.get_key_name(self.hotkey_rec)}",
            command=lambda: self.start_mapping("rec", self.lbl_rec),
            scale=UI_SCALE, palette=UI,
        )
        self.lbl_rec.pack(fill="x", padx=px(18), pady=px(3))
        self.lbl_play = AdwRow(
            self.settings_frame,
            text=f"Play/Stop: {self.get_key_name(self.hotkey_play)}",
            command=lambda: self.start_mapping("play", self.lbl_play),
            scale=UI_SCALE, palette=UI,
        )
        self.lbl_play.pack(fill="x", padx=px(18), pady=px(3))
        self._switch_row("Humanize", self.humanize_enabled,
                         padx=px(18), pady=(px(12), 0))
        if updater.appimage_path() is not None:
            self._build_updates_section()
        # Measured on the next loop turn, not inline: the canvas rows only
        # publish their requested size once their first redraw has run, so an
        # inline measurement came out ~100 px short in the Updates section.
        self.settings_win.after(0, self._fit_settings_height)

    def _fit_settings_height(self, attempt=0):
        """Makes the Settings window exactly as tall as its packed rows.

        Re-armed while the content keeps asking for a new height: resizing the
        window re-lays-out the rows, which can reveal one more request (the
        progress bar). Stops on the first unchanged measurement, so it cannot
        ping-pong, and after 4 turns it leaves whatever it has.
        """
        if not (hasattr(self, "settings_win")
                and self.settings_win.winfo_exists()):
            return
        need = self.settings_frame.winfo_reqheight()
        if not need or need == getattr(self, "_settings_height", None):
            return
        self._settings_height = need
        self.settings_win.geometry("%dx%d" % (px(300), need))
        if attempt < 4:
            self.settings_win.after(
                0, lambda: self._fit_settings_height(attempt + 1))

    def _section_title(self, text, padx=None, pady=None):
        """Bold page heading, the way a preferences section opens."""
        tkinter.Label(
            self.settings_frame, text=text, bg=UI_WINDOW_BG,
            fg=UI.window_fg, anchor="w",
            font=("DejaVu Sans", int(round(13 * UI_SCALE)), "bold"),
        ).pack(fill="x", padx=padx if padx is not None else px(18),
               pady=pady if pady is not None else (px(16), px(2)))

    def _switch_row(self, label, variable, command=None, padx=None,
                    pady=None):
        """A label on the left and an Adwaita switch on the right."""
        row = tkinter.Frame(self.settings_frame, bg=UI_WINDOW_BG)
        # The bottom margin is part of the row: the window is now exactly as
        # tall as its content, so without it the switch sits on the edge.
        row.pack(fill="x", padx=padx if padx is not None else px(18),
                 pady=pady if pady is not None else (px(12), px(14)))
        tkinter.Label(
            row, text=label, bg=UI_WINDOW_BG, fg=UI.window_fg, anchor="w",
            font=("DejaVu Sans", int(round(10 * UI_SCALE))),
        ).pack(side="left", fill="x", expand=True)
        AdwSwitch(
            row, variable=variable, command=command,
            scale=UI_SCALE, palette=UI,
        ).pack(side="right")

    def _close_settings(self):
        self.is_mapping = None
        self.settings_win.destroy()

    def start_mapping(self, mode, btn):
        """Starts hotkey mapping mode."""
        self.is_mapping = mode
        btn.configure(text="Press any key...", fg_color=MAPPING_FILL)

    def toggle_loop(self):
        """Toggles loop playback mode."""
        self.loop_enabled = not self.loop_enabled
        self.btn_loop.configure(
            # Loop state is shown by color (blue = on), so one glyph suffices.
            text="↻",
            fg_color=LOOP_FILL if self.loop_enabled else UI_NEUTRAL
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
            with open(self._config_path(), encoding="utf-8") as fh:
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

    # --- AppImage updates ---------------------------------------------
    # Scope is the AppImage only: updater.appimage_path() is the gate, and
    # when it answers None there is no badge, no Settings section and no
    # network call. Tk is touched only from the UI thread -- workers store
    # plain attributes and queue a token, exactly like _driver_warn_fn.

    def _start_update_check(self, force=False):
        """Starts the check worker, or returns False when it is not due.

        `force` is the Settings `Check now` button: a manual action skips
        both the 24 h throttle and the automatic switch, because a user
        who asks deserves an answer.
        """
        if self.__dict__.get("_update_check_running"):
            return False
        if updater.appimage_path() is None:
            return False
        cfg = self.__dict__.get("app_config") or {}
        if not force:
            if cfg.get("update_check_enabled") is False:
                return False
            try:
                last = float(cfg.get("update_last_check") or 0)
            except (TypeError, ValueError):
                last = 0.0
            if time.time() - last < updater.CHECK_INTERVAL_SECONDS:
                return False
        self._update_check_running = True
        self._update_manual = bool(force)
        threading.Thread(
            target=self._update_check_worker, args=(bool(force),),
            daemon=True,
        ).start()
        return True

    def _update_check_worker(self, manual=False):
        """Worker thread: no Tk, one attribute write and one queue token."""
        info = None
        try:
            info = updater.fetch_latest()
        except Exception:  # a worker must never kill the app
            logger.debug("Update check raised.", exc_info=True)
        self._update_info = info
        self._update_manual = manual
        self._ui_queue.put("update_checked")

    def _handle_update_checked(self):
        """UI thread: persist the check time and show only what is news."""
        self._update_check_running = False
        info = self.__dict__.get("_update_info")
        manual = bool(self.__dict__.get("_update_manual"))
        cfg = self.__dict__.get("app_config")
        if cfg is None:
            cfg = self.app_config = {}
        cfg["update_last_check"] = time.time()
        self._save_app_config()
        newer = bool(info is not None
                     and updater.is_newer(info.version, APP_VERSION))
        self._update_available = newer
        if newer:
            # The loop button's blue: a badge, never a dialog.
            btn = self.__dict__.get("btn_settings")
            if btn is not None:
                try:
                    btn.configure(fg_color=LOOP_FILL)
                except Exception:  # a dead widget is not fatal
                    logger.debug("Could not recolour the settings button.",
                                 exc_info=True)
            self._set_update_tooltip("Update available: v%s" % info.version)
            self._update_status = "v%s is available." % info.version
        if manual:
            if info is None:
                self._update_status = (
                    "Could not reach GitHub. Try again later.")
            elif not newer:
                self._update_status = (
                    "Already up to date (v%s)." % APP_VERSION)
        self._refresh_update_widgets()

    def _set_update_tooltip(self, text):
        """Replaces the Settings button tooltip text (ToolTip reads it live)."""
        tip = self.__dict__.get("_update_tooltip")
        if tip is not None:
            tip.text = text
            return
        btn = self.__dict__.get("btn_settings")
        if btn is None:
            return
        try:
            self._update_tooltip = ToolTip(btn, text)
        except Exception:  # tooltips are decoration
            logger.debug("Could not set the update tooltip.", exc_info=True)

    def _settings_widget(self, name):
        """The Settings widget `name`, or None if that window is gone."""
        widget = self.__dict__.get(name)
        if widget is None:
            return None
        try:
            if not widget.winfo_exists():
                return None
        except Exception:  # mocks and destroyed widgets
            return None
        return widget

    def _update_download_label(self):
        """The install button's label, which depends on where it can write."""
        target = updater.appimage_path()
        if target is None:
            return "Save to\u2026"
        if os.access(os.path.dirname(target) or ".", os.W_OK):
            return "Download and install"
        return "Save to\u2026"

    def _refresh_update_widgets(self):
        """Pushes the stored update state onto the Settings widgets."""
        label = self._settings_widget("update_status_lbl")
        if label is not None:
            label.configure(text=self.__dict__.get("_update_status") or "")
        button = self._settings_widget("btn_update_download")
        if button is None:
            return
        if self.__dict__.get("_update_downloading"):
            button.configure(state="disabled")
        elif (self.__dict__.get("_update_available")
              and not self.__dict__.get("_update_installed")):
            button.configure(state="normal",
                             text=self._update_download_label())
        else:
            button.configure(state="disabled")

    def _start_update_download(self):
        """Starts the download worker; one download at a time."""
        if self.__dict__.get("_update_downloading"):
            return False
        info = self.__dict__.get("_update_info")
        if info is None:
            return False
        target = updater.appimage_path()
        if target is None:
            return False
        if not os.access(os.path.dirname(target) or ".", os.W_OK):
            # Read-only install location: write the new bundle elsewhere
            # and leave the running file alone.
            try:
                chosen = filedialog.asksaveasfilename(
                    title="Save the new AppImage",
                    initialfile=os.path.basename(target),
                    defaultextension=".AppImage",
                )
            except Exception:  # no display, dead widget
                logger.debug("Save dialog failed.", exc_info=True)
                return False
            if not chosen:
                return False
            target = chosen
        self._update_downloading = True
        self._update_installed = False
        self._update_error = None
        self._update_target = target
        self._update_last_percent = -1
        self._update_progress = (0, 0)
        self._update_status = "Downloading\u2026"
        self._refresh_update_widgets()
        threading.Thread(
            target=self._update_download_worker, args=(info, target),
            daemon=True,
        ).start()
        return True

    def _update_download_worker(self, info, target):
        """Worker thread: streams the asset, then reports with a token."""
        try:
            updater.download(info, target, progress=self._note_update_progress)
        except Exception as exc:  # UpdateError, or anything unforeseen
            logger.debug("Update download failed: %s", exc)
            self._update_error = str(exc) or "Download failed."
            self._ui_queue.put("update_failed")
            return
        self._ui_queue.put("update_installed")

    def _note_update_progress(self, done, total):
        """Called by the download in the worker thread, once per percent."""
        self._update_progress = (done, total or 1)
        percent = int(done * 100 / (total or 1))
        if percent != self.__dict__.get("_update_last_percent"):
            self._update_last_percent = percent
            self._ui_queue.put("update_progress")

    def _handle_update_progress(self):
        bar = self._settings_widget("update_progress_bar")
        if bar is None:
            return
        done, total = self.__dict__.get("_update_progress", (0, 0))
        try:
            bar.set(min(1.0, done / (total or 1)))
        except Exception:  # a dead widget is not fatal
            logger.debug("Could not update the progress bar.", exc_info=True)

    def _handle_update_installed(self):
        self._update_downloading = False
        self._update_installed = True
        info = self.__dict__.get("_update_info")
        version = info.version if info is not None else "the new version"
        target = self.__dict__.get("_update_target")
        running = updater.appimage_path()
        if target and running and \
                os.path.abspath(target) != os.path.abspath(running):
            self._update_status = (
                "Saved to %s. Run it when you are ready." % target)
        else:
            # No auto-relaunch: killing a session mid-macro is worse than
            # one click on the icon.
            self._update_status = (
                "Restart LinuxTask to use v%s." % version)
        bar = self._settings_widget("update_progress_bar")
        if bar is not None:
            try:
                bar.set(1.0)
            except Exception:  # a dead widget is not fatal
                logger.debug("Could not finish the progress bar.",
                             exc_info=True)
        self._refresh_update_widgets()

    def _handle_update_failed(self):
        self._update_downloading = False
        self._update_status = (
            self.__dict__.get("_update_error") or "Download failed.")
        self._refresh_update_widgets()

    def _toggle_update_auto(self):
        """Persists the `Check automatically` checkbox."""
        cfg = self.__dict__.get("app_config")
        if cfg is None:
            cfg = self.app_config = {}
        cfg["update_check_enabled"] = bool(self.update_auto_var.get())
        self._save_app_config()

    def _build_updates_section(self):
        """The Updates block of the Settings window (AppImage only)."""
        self._section_title("Updates", padx=px(18), pady=(px(18), px(2)))
        self.update_version_lbl = tkinter.Label(
            self.settings_frame,
            text="Current version: v%s" % APP_VERSION,
            bg=UI_WINDOW_BG, fg=UI.dim, anchor="w",
            font=("DejaVu Sans", int(round(9 * UI_SCALE))),
        )
        self.update_version_lbl.pack(fill="x", padx=px(18))
        self.update_status_lbl = tkinter.Label(
            self.settings_frame, text="", wraplength=px(256), justify="left",
            bg=UI_WINDOW_BG, fg=UI.window_fg, anchor="w",
            font=("DejaVu Sans", int(round(9 * UI_SCALE))),
        )
        self.update_status_lbl.pack(fill="x", padx=px(18), pady=(px(4), px(8)))
        self.update_progress_bar = AdwProgress(
            self.settings_frame, height=6, scale=UI_SCALE, palette=UI)
        self.update_progress_bar.set(0)
        self.update_progress_bar.pack(fill="x", padx=px(18), pady=(0, px(8)))
        # Fixed width rather than fill="x": the canvas paints its own raster,
        # so it has to know its size up front instead of being stretched.
        button_width = 300 - 2 * 18
        self.btn_update_check = AdwButton(
            self.settings_frame, text="Check now",
            width=button_width, height=34, raised=True,
            font=("DejaVu Sans", 10), scale=UI_SCALE, palette=UI,
            command=lambda: self._start_update_check(force=True),
        )
        self.btn_update_check.pack(padx=px(18), pady=px(3))
        self.btn_update_download = AdwButton(
            self.settings_frame, text="Download and install",
            width=button_width, height=34, raised=True,
            font=("DejaVu Sans", 10), scale=UI_SCALE, palette=UI,
            command=self._start_update_download,
        )
        self.btn_update_download.pack(padx=px(18), pady=px(3))
        cfg = self.__dict__.get("app_config") or {}
        self.update_auto_var = ctk.BooleanVar(
            value=cfg.get("update_check_enabled") is not False)
        self._switch_row("Check automatically", self.update_auto_var,
                         command=self._toggle_update_auto,
                         padx=px(18), pady=(px(8), 0))
        self._refresh_update_widgets()

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
                font=("DejaVu Sans", 12),
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

    def _bind_playback_settings(self):
        """Mirrors the Tk playback switches into plain python attributes.

        Tk is single-threaded, so the playback worker must not call
        speed_var.get()/humanize_enabled.get() — that is an unguarded Tcl
        round trip from another thread. The traces below run on the UI
        thread, so the worker reads plain float/bool attributes and a
        mid-playback change still takes effect (see playback.py
        _setting_speed/_setting_humanize).
        """
        def _sync_speed(*_args):
            try:
                self._speed_value = float(
                    str(self.speed_var.get()).replace("x", "").strip())
            except (ValueError, TypeError):
                self._speed_value = 1.0

        def _sync_humanize(*_args):
            self._humanize_value = bool(self.humanize_enabled.get())

        _sync_speed()
        _sync_humanize()
        self.speed_var.trace_add("write", _sync_speed)
        self.humanize_enabled.trace_add("write", _sync_humanize)

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
            self.start_cursor_pos = self.manager.get_cursor_pos()
            # monotonic: event timestamps below are deltas from this base,
            # so a clock jump mid-recording must not skew them.
            self.start_time = time.monotonic()
            # Arm last. device_loop captures whenever self.recording is
            # True, so setting it before the base existed gave the first
            # events a negative time (monotonic() - a later start_time)
            # and let the recorder read a position we were still changing.
            self.recording = True
            with self.events_lock:
                self._rel_dirty = False
                self._rel_dx = 0
                self._rel_dy = 0
                self.events = []
            with self._processed_ids_lock:
                self._processed_ids.clear()
                # __dict__ lookup: see note in device_loop.
                order = self.__dict__.get("_processed_ids_order")
                if order is not None:
                    order.clear()
            self.rec_tip = ToolTip(
                self.btn_rec, RECORDING_TOOLTIP_TEXT)
            self.btn_rec.configure(text="■", fg_color=RECORDING_FILL)
            logger.info(
                "Recording started. Start pos: %s",
                self.start_cursor_pos
            )
        else:
            self.recording = False
            self.rec_tip = ToolTip(self.btn_rec, "Record (F8)")
            self.btn_rec.configure(text="●", fg_color=RECORDING_FILL)
            with self.events_lock:
                ev_count = len(self.events)
            logger.info("Recording stopped. %d events captured.", ev_count)

    def get_key_name(self, code):
        """Returns human-readable key name from evdev code."""
        name = evdev.ecodes.KEY.get(code, str(code))
        if isinstance(name, list):
            name = name[0]
        return name


def main(argv=None):
    """Entry point (also used by the AppImage console script).

    No arguments starts the GUI. Anything else goes to the headless CLI in
    cli.py, so `play <macro.json>` replays without opening a window
    (issue #5), and an unknown flag or a misspelled subcommand is answered
    by argparse with exit 2 instead of by a window appearing. Neither
    launcher passes arguments: the desktop entries run `AppRun` and the
    installed `tools/run.sh` bare.
    """
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        from cli import main as cli_main
        return cli_main(argv)
    try:
        app = LinuxTaskApp()
    except RuntimeError as exc:
        # Missing system deps or an unsupported desktop: a visible dialog
        # and a clean exit code, not a traceback in a terminal nobody sees.
        logger.error("Driver initialization failed: %s", exc)
        try:
            import tkinter.messagebox as mb
            mb.showerror("LinuxTask - Initialization failed", str(exc))
        except Exception:
            logger.debug("Failed to show error dialog.", exc_info=True)
        return 1
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
