# -*- coding: utf-8 -*-
"""
LinuxTask - playback.py
Description: Playback half of the app (playback thread, humanize, event
             validation and macro persistence), moved out of main.py.
             Methods are mixed into LinuxTaskApp, so the public surface
             is unchanged.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import os
import json
import time
import random
import threading
import logging
import traceback

import evdev
from evdev import ecodes as e
from tkinter import filedialog

logger = logging.getLogger("LinuxTask")


class Playback:
    """Playback methods; state (events, playing flag, driver) lives on the app."""

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
        # playback_thread reads ev['time'] for every event before
        # dispatching it, so a non-numeric 'time' there aborts the whole
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
