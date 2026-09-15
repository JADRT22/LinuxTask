# -*- coding: utf-8 -*-
"""
LinuxTask - test_main_flow.py
Description: Headless unit tests for the core app flow in src/main.py
             (recording via device_loop, playback dispatch, persistence,
             event validation, hotkey queue). No display or hardware
             required: LinuxTaskApp is instantiated via __new__, bypassing
             customtkinter's __init__, and only the pure logic paths are
             exercised.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import json
import os
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import main  # noqa: E402  (imports customtkinter/evdev, but no display touched)
from evdev import ecodes as e  # noqa: E402
from evdev.events import InputEvent  # noqa: E402


def make_app():
    """Builds a bare LinuxTaskApp without running CTk.__init__ (no display)."""
    app = main.LinuxTaskApp.__new__(main.LinuxTaskApp)
    app.recording = False
    app.playing = False
    app.loop_enabled = False
    app.events = []
    app.events_lock = threading.Lock()
    app.start_time = 0.0
    app.start_cursor_pos = None
    app.recording = False
    app.hotkey_rec = e.KEY_F8
    app.hotkey_play = e.KEY_F9
    app.is_mapping = None
    app._rel_dx = 0
    app._rel_dy = 0
    app._rel_dirty = False
    app._processed_ids = set()
    app._processed_ids_lock = threading.Lock()
    app._ui_queue = __import__('queue').Queue()
    app.uinput_device = None
    app.humanize_enabled = MagicMock(return_value=False)
    app.humanize_enabled.get.return_value = False
    app.manager = MagicMock()
    app.manager.supports_absolute_positioning = True
    app.manager.get_cursor_pos.return_value = (100, 200)
    app.btn_rec = MagicMock()
    app.btn_play = MagicMock()
    app.btn_loop = MagicMock()
    app.lbl_rec = MagicMock()
    app.lbl_play = MagicMock()
    app.speed_var = MagicMock()
    app.speed_var.get.return_value = "1x"
    return app


def make_event(etype, code, value, sec=None, usec=0):
    """Builds an evdev InputEvent with unique monotonic timestamps."""
    if sec is None:
        sec = time.monotonic()
    return InputEvent(sec=sec, usec=usec, type=etype, code=code, value=value)


class FakeDevice:
    """Minimal stand-in for evdev.InputDevice in device_loop."""

    def __init__(self, events, name="Fake Device"):
        self._events = list(events)
        self.name = name

    def read_loop(self):
        yield from self._events


class TestEventDeduplication(unittest.TestCase):
    """The same physical event arrives on multiple /dev/input/event*
    devices; device_loop dedupes by (sec, usec, type, code, value)."""

    def setUp(self):
        self.app = make_app()

    def test_duplicate_event_across_devices_recorded_once(self):
        self.app.toggle_record()
        self.assertTrue(self.app.recording)

        ev = make_event(e.EV_KEY, e.KEY_A, 1)
        # Two devices see the exact same (sec, usec, type, code, value).
        self.app.device_loop(FakeDevice([ev]))
        self.app.device_loop(FakeDevice([ev]))

        with self.app.events_lock:
            keys = [ev2 for ev2 in self.app.events if ev2["type"] == "key"]
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0]["code"], e.KEY_A)

    def test_distinct_events_both_recorded(self):
        self.app.toggle_record()
        base = time.monotonic()
        self.app.device_loop(FakeDevice([
            make_event(e.EV_KEY, e.KEY_A, 1, sec=base),
            make_event(e.EV_KEY, e.KEY_A, 0, sec=base + 0.01),
        ]))
        with self.app.events_lock:
            keys = [ev2 for ev2 in self.app.events if ev2["type"] == "key"]
        self.assertEqual(len(keys), 2)


class TestRecordingFlow(unittest.TestCase):
    def setUp(self):
        self.app = make_app()

    def test_key_press_and_release_are_recorded(self):
        self.app.toggle_record()
        base = time.monotonic()
        self.app.device_loop(FakeDevice([
            make_event(e.EV_KEY, e.KEY_H, 1, sec=base),
            make_event(e.EV_KEY, e.KEY_H, 0, sec=base + 0.05),
        ]))
        self.app.recording = False  # stop without touching the button mock

        with self.app.events_lock:
            keys = [ev2 for ev2 in self.app.events if ev2["type"] == "key"]
        self.assertEqual(len(keys), 2)
        self.assertEqual([k["val"] for k in keys], [1, 0])

    def test_hotkeys_are_not_recorded(self):
        self.app.toggle_record()
        base = time.monotonic()
        self.app.device_loop(FakeDevice([
            make_event(e.EV_KEY, self.app.hotkey_rec, 1, sec=base),
            make_event(e.EV_KEY, e.KEY_A, 1, sec=base + 0.01),
            make_event(e.EV_KEY, self.app.hotkey_play, 1, sec=base + 0.02),
        ]))
        with self.app.events_lock:
            keys = [ev2 for ev2 in self.app.events if ev2["type"] == "key"]
        self.assertEqual([k["code"] for k in keys], [e.KEY_A])

    def test_hotkey_press_enqueues_ui_action(self):
        self.app.toggle_record()  # not strictly needed; hotkeys fire always
        self.app.recording = False
        self.app.device_loop(FakeDevice([
            make_event(e.EV_KEY, self.app.hotkey_play, 1),
        ]))
        self.assertEqual(self.app._ui_queue.get_nowait(), "play")
        with self.assertRaises(__import__('queue').Empty):
            self.app._ui_queue.get_nowait()

    def test_relative_motion_accumulates_and_flushes_on_syn(self):
        self.app.manager.supports_absolute_positioning = False
        self.app.toggle_record()
        base = time.monotonic()
        self.app.device_loop(FakeDevice([
            make_event(e.EV_REL, e.REL_X, 5, sec=base),
            make_event(e.EV_REL, e.REL_Y, -3, sec=base),
            make_event(e.EV_SYN, e.SYN_REPORT, 0, sec=base + 0.01),
        ]))
        with self.app.events_lock:
            rels = [ev2 for ev2 in self.app.events if ev2["type"] == "rel"]
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]["dx"], 5)
        self.assertEqual(rels[0]["dy"], -3)
        # Accumulators reset after flush.
        self.assertEqual(self.app._rel_dx, 0)
        self.assertEqual(self.app._rel_dy, 0)

    def test_absolute_mode_flushes_pos_on_syn(self):
        self.app.manager.supports_absolute_positioning = True
        self.app.toggle_record()
        base = time.monotonic()
        self.app.device_loop(FakeDevice([
            make_event(e.EV_REL, e.REL_X, 7, sec=base),
            make_event(e.EV_SYN, e.SYN_REPORT, 0, sec=base + 0.01),
        ]))
        with self.app.events_lock:
            poss = [ev2 for ev2 in self.app.events if ev2["type"] == "pos"]
        self.assertEqual(len(poss), 1)
        self.assertEqual(poss[0]["x"], 100)
        self.assertEqual(poss[0]["y"], 200)
        self.app.manager.get_cursor_pos.assert_called()

    def test_scroll_recorded_with_direction_and_clicks(self):
        self.app.toggle_record()
        base = time.monotonic()
        self.app.device_loop(FakeDevice([
            make_event(e.EV_REL, e.REL_WHEEL, 1, sec=base),   # up
            make_event(e.EV_REL, e.REL_WHEEL, -2, sec=base + 0.01),  # down x2
        ]))
        with self.app.events_lock:
            scrolls = [ev2 for ev2 in self.app.events if ev2["type"] == "scroll"]
        self.assertEqual(len(scrolls), 2)
        self.assertEqual(scrolls[0]["direction"], "up")
        self.assertEqual(scrolls[0]["clicks"], 1)
        self.assertEqual(scrolls[1]["direction"], "down")
        self.assertEqual(scrolls[1]["clicks"], 2)

    def test_nothing_recorded_when_not_recording(self):
        self.app.device_loop(FakeDevice([
            make_event(e.EV_KEY, e.KEY_A, 1),
            make_event(e.EV_REL, e.REL_X, 10),
            make_event(e.EV_SYN, e.SYN_REPORT, 0),
        ]))
        self.assertEqual(self.app.events, [])

    def test_toggle_record_resets_state(self):
        self.app.events = [{"type": "key", "code": 1, "val": 1, "time": 0.1}]
        self.app._rel_dx = 9
        self.app._rel_dy = 9
        self.app._processed_ids.add((0, 0, 0, 0, 0))
        self.app.start_cursor_pos = (1, 1)

        self.app.toggle_record()

        self.assertTrue(self.app.recording)
        self.assertEqual(self.app.events, [])
        self.assertEqual(self.app._rel_dx, 0)
        self.assertEqual(self.app._rel_dy, 0)
        self.assertEqual(self.app._processed_ids, set())
        self.app.manager.get_cursor_pos.assert_called_once()

    def test_toggle_record_while_playing_is_ignored(self):
        self.app.playing = True
        self.app.toggle_record()
        self.assertFalse(self.app.recording)


class TestHotkeyMapping(unittest.TestCase):
    def setUp(self):
        self.app = make_app()

    def test_mapping_rec_hotkey_updates_code_and_label(self):
        self.app.is_mapping = "rec"
        base = time.monotonic()
        self.app.device_loop(FakeDevice([
            make_event(e.EV_KEY, e.KEY_F2, 1, sec=base),
        ]))
        self.assertEqual(self.app.hotkey_rec, e.KEY_F2)
        self.assertIsNone(self.app.is_mapping)
        self.app.lbl_rec.configure.assert_called()

    def test_esc_cancels_mapping(self):
        self.app.is_mapping = "play"
        base = time.monotonic()
        self.app.device_loop(FakeDevice([
            make_event(e.EV_KEY, e.KEY_ESC, 1, sec=base),
        ]))
        self.assertEqual(self.app.hotkey_play, e.KEY_F9)  # unchanged
        self.assertIsNone(self.app.is_mapping)

    def test_mapping_mode_does_not_record_key(self):
        self.app.toggle_record()
        self.app.is_mapping = "rec"
        base = time.monotonic()
        self.app.device_loop(FakeDevice([
            make_event(e.EV_KEY, e.KEY_F2, 1, sec=base),
        ]))
        with self.app.events_lock:
            keys = [ev2 for ev2 in self.app.events if ev2["type"] == "key"]
        self.assertEqual(keys, [])


class TestHumanize(unittest.TestCase):
    def setUp(self):
        self.app = make_app()

    def test_disabled_returns_values_unchanged(self):
        self.app.humanize_enabled.get.return_value = False
        dx, dy, delay = self.app._apply_humanize(10, 20, 0.5)
        self.assertEqual((dx, dy, delay), (10, 20, 0.5))

    def test_enabled_jitter_bounded_and_delay_increased(self):
        self.app.humanize_enabled.get.return_value = True
        for _ in range(50):
            dx, dy, delay = self.app._apply_humanize(10, 20, 0.5)
            self.assertTrue(8 <= dx <= 12, f"dx out of bounds: {dx}")
            self.assertTrue(18 <= dy <= 22, f"dy out of bounds: {dy}")
            self.assertTrue(0.5 <= delay <= 0.5 * 1.03 + 1e-9,
                            f"delay out of bounds: {delay}")

    def test_jitter_is_not_always_zero(self):
        self.app.humanize_enabled.get.return_value = True
        xs = {self.app._apply_humanize(10, 10, 0)[0] for _ in range(100)}
        self.assertGreater(len(xs), 1)


class TestPlaybackDispatch(unittest.TestCase):
    """Runs playback_thread against mock driver/uinput and verifies dispatch."""

    def setUp(self):
        self.app = make_app()
        self.app.start_cursor_pos = (100, 200)
        self.app.start_time = time.monotonic()
        self.app.events = [
            {"type": "pos", "x": 300, "y": 400, "time": 0.0},
            {"type": "rel", "dx": 5, "dy": -5, "time": 0.0},
            {"type": "scroll", "direction": "down", "clicks": 2, "time": 0.0},
            {"type": "key", "code": e.KEY_A, "val": 1, "time": 0.0},
            {"type": "key", "code": e.BTN_LEFT, "val": 1, "time": 0.0},
            {"type": "key", "code": e.BTN_LEFT, "val": 0, "time": 0.0},
        ]

    def test_all_event_types_dispatched_to_driver_or_uinput(self):
        self.app.uinput_device = MagicMock()
        self.app.manager.move_relative.return_value = False  # force fallback
        self.app.manager.mouse_button.return_value = False
        self.app.manager.scroll.return_value = False

        self.app.start_playback()
        # Wait for the playback thread to finish.
        deadline = time.monotonic() + 5
        while self.app.playing and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.app.playing)

        self.app.manager.move_cursor.assert_any_call(100, 200)
        self.app.manager.move_cursor.assert_any_call(300, 400)
        self.app.manager.move_relative.assert_called_once_with(5, -5)

        # rel fell back to UInput (driver declined).
        writes = self.app.uinput_device.write.call_args_list
        rel_writes = [c for c in writes if c.args[0] == e.EV_REL]
        self.assertIn((e.EV_REL, e.REL_X, 5), [c.args for c in rel_writes])
        self.assertIn((e.EV_REL, e.REL_Y, -5), [c.args for c in rel_writes])

        # scroll fell back to UInput: 2 clicks of REL_WHEEL -1.
        wheel_writes = [c.args for c in writes if c.args[0] == e.EV_REL
                        and c.args[1] == e.REL_WHEEL]
        self.assertEqual(wheel_writes, [(e.EV_REL, e.REL_WHEEL, -1),
                                        (e.EV_REL, e.REL_WHEEL, -1)])

        # mouse button: driver declined -> UInput gets press and release.
        key_writes = [c.args for c in writes if c.args[0] == e.EV_KEY]
        self.assertIn((e.EV_KEY, e.BTN_LEFT, 1), key_writes)
        self.assertIn((e.EV_KEY, e.BTN_LEFT, 0), key_writes)

        # plain key always via UInput.
        self.assertIn((e.EV_KEY, e.KEY_A, 1), key_writes)
        self.assertTrue(self.app.uinput_device.syn.called)

        # UI reset was queued (thread-safe path).
        self.assertEqual(self.app._ui_queue.get_nowait(), "play_finished")

    def test_driver_handled_rel_and_button_skip_uinput(self):
        self.app.uinput_device = MagicMock()
        self.app.manager.move_relative.return_value = True
        self.app.manager.mouse_button.return_value = True

        self.app.start_playback()
        deadline = time.monotonic() + 5
        while self.app.playing and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.app.playing)

        self.app.manager.move_relative.assert_called_once_with(5, -5)
        writes = self.app.uinput_device.write.call_args_list
        self.assertEqual([c.args for c in writes if c.args[0] == e.EV_REL],
                         [])  # no REL fallback
        self.assertNotIn((e.EV_KEY, e.BTN_LEFT, 1),
                         [c.args for c in writes if c.args[0] == e.EV_KEY])
        # Plain key still goes through UInput.
        self.assertIn((e.EV_KEY, e.KEY_A, 1),
                      [c.args for c in writes if c.args[0] == e.EV_KEY])

    def test_playback_finishes_with_uinput_none_and_queues_reset(self):
        # uinput_device stays None: rel/scroll/buttons are dropped with
        # warnings, plain keys are skipped. Must not crash.
        self.app.manager.move_relative.return_value = False
        self.app.manager.mouse_button.return_value = False
        self.app.manager.scroll.return_value = False

        self.app.start_playback()
        deadline = time.monotonic() + 5
        while self.app.playing and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.app.playing)
        self.assertEqual(self.app._ui_queue.get_nowait(), "play_finished")

    def test_speed_divides_event_times(self):
        self.app.events = [
            {"type": "pos", "x": 1, "y": 2, "time": 2.0},
        ]
        self.app.speed_var.get.return_value = "4x"
        self.app.manager.move_relative.return_value = True

        started = time.monotonic()
        self.app.start_playback()
        deadline = time.monotonic() + 5
        while self.app.playing and time.monotonic() + deadline:
            time.sleep(0.01)
        elapsed = time.monotonic() - started
        # 2.0s / 4x = 0.5s scheduled; allow generous CI slack.
        self.assertLess(elapsed, 1.5)
        self.assertGreaterEqual(elapsed, 0.4)

    def test_stop_flag_interrupts_playback(self):
        self.app.events = [
            {"type": "key", "code": e.KEY_A, "val": 1, "time": 0.0},
            {"type": "key", "code": e.KEY_B, "val": 1, "time": 5.0},
        ]
        self.app.start_playback()
        # Give the thread a moment to start, then demand a stop.
        deadline = time.monotonic() + 5
        while not self.app.playing and time.monotonic() < deadline:
            time.sleep(0.005)
        self.app.playing = False
        deadline = time.monotonic() + 5
        while self.app.playing and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.app.playing)
        # The 5s-away event must NOT have been replayed.
        writes = self.app.uinput_device.write.call_args_list \
            if self.app.uinput_device else []
        self.assertEqual(writes, [])

    def test_sync_for_playback_called_when_available(self):
        self.app.manager.sync_for_playback = MagicMock()
        self.app.start_playback()
        deadline = time.monotonic() + 5
        while self.app.playing and time.monotonic() < deadline:
            time.sleep(0.01)
        self.app.manager.sync_for_playback.assert_called_once()

    def test_playback_with_no_events_is_noop(self):
        self.app.events = []
        self.app.start_playback()
        self.assertFalse(self.app.playing)
        self.app.btn_play.configure.assert_not_called()


class TestEventValidation(unittest.TestCase):
    def setUp(self):
        self.app = make_app()

    def test_valid_pos_event(self):
        self.assertTrue(self.app._validate_event(
            {"type": "pos", "x": 1, "y": 2}))

    def test_valid_rel_event(self):
        self.assertTrue(self.app._validate_event(
            {"type": "rel", "dx": 1.5, "dy": -2}))

    def test_valid_scroll_event(self):
        self.assertTrue(self.app._validate_event(
            {"type": "scroll", "direction": "up", "clicks": 3}))
        # clicks optional, defaults to 1
        self.assertTrue(self.app._validate_event(
            {"type": "scroll", "direction": "down"}))

    def test_valid_key_event(self):
        self.assertTrue(self.app._validate_event(
            {"type": "key", "code": 30, "val": 1}))

    def test_invalid_events_rejected(self):
        bad = [
            "not a dict",
            {"type": "unknown"},
            {"type": "pos", "x": "1", "y": 2},          # str x
            {"type": "pos", "y": 2},                     # missing x
            {"type": "rel", "dx": 1},                    # missing dy
            {"type": "scroll", "direction": "sideways"},  # bad direction
            {"type": "key", "code": "30", "val": 1},     # str code
            {},                                          # missing type
        ]
        for ev in bad:
            self.assertFalse(self.app._validate_event(ev), f"accepted {ev!r}")


class TestPersistence(unittest.TestCase):
    def setUp(self):
        self.app = make_app()

    def _write_macro(self, path, data):
        with open(path, 'w') as fp:
            json.dump(data, fp)

    def test_open_file_roundtrip(self):
        import tempfile
        macro = {
            "start_pos": [10, 20],
            "events": [
                {"type": "pos", "x": 1, "y": 2, "time": 0.0},
                {"type": "key", "code": 30, "val": 1, "time": 0.1},
            ],
        }
        with tempfile.NamedTemporaryFile('w', suffix='.json',
                                         delete=False) as fp:
            json.dump(macro, fp)
            tmp = fp.name
        try:
            with patch('main.filedialog.askopenfilename', return_value=tmp):
                self.app.open_file()
        finally:
            os.unlink(tmp)

        self.assertEqual(self.app.start_cursor_pos, (10, 20))
        with self.app.events_lock:
            self.assertEqual(len(self.app.events), 2)

    def test_open_file_filters_invalid_events(self):
        import tempfile
        macro = {
            "start_pos": [5, 6],
            "events": [
                {"type": "pos", "x": 1, "y": 2, "time": 0.0},
                {"garbage": True},
                {"type": "key", "code": "oops", "val": 1, "time": 0.2},
                {"type": "rel", "dx": 3, "dy": 4, "time": 0.3},
            ],
        }
        with tempfile.NamedTemporaryFile('w', suffix='.json',
                                         delete=False) as fp:
            json.dump(macro, fp)
            tmp = fp.name
        try:
            with patch('main.filedialog.askopenfilename', return_value=tmp):
                self.app.open_file()
        finally:
            os.unlink(tmp)

        with self.app.events_lock:
            self.assertEqual(len(self.app.events), 2)
        self.assertEqual(self.app.start_cursor_pos, (5, 6))

    def test_open_file_legacy_list_format(self):
        import tempfile
        events = [{"type": "key", "code": 30, "val": 1, "time": 0.0}]
        with tempfile.NamedTemporaryFile('w', suffix='.json',
                                         delete=False) as fp:
            json.dump(events, fp)
            tmp = fp.name
        try:
            with patch('main.filedialog.askopenfilename', return_value=tmp):
                self.app.open_file()
        finally:
            os.unlink(tmp)

        with self.app.events_lock:
            self.assertEqual(len(self.app.events), 1)
        self.assertIsNone(self.app.start_cursor_pos)

    def test_open_file_rejects_non_list_events(self):
        import tempfile
        with tempfile.NamedTemporaryFile('w', suffix='.json',
                                         delete=False) as fp:
            json.dump({"events": "nope"}, fp)
            tmp = fp.name
        try:
            with patch('main.filedialog.askopenfilename', return_value=tmp):
                self.app.open_file()  # must not raise
        finally:
            os.unlink(tmp)
        with self.app.events_lock:
            self.assertEqual(self.app.events, [])

    def test_open_file_handles_missing_file(self):
        with patch('main.filedialog.askopenfilename',
                   return_value='/nonexistent/macro.json'):
            self.app.open_file()  # must not raise
        with self.app.events_lock:
            self.assertEqual(self.app.events, [])

    def test_save_file_writes_start_pos_and_events(self):
        import tempfile
        self.app.start_cursor_pos = (7, 8)
        self.app.events = [
            {"type": "pos", "x": 1, "y": 2, "time": 0.0},
            {"type": "key", "code": 30, "val": 1, "time": 0.1},
        ]
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, 'macro.json')
        with patch('main.filedialog.asksaveasfilename', return_value=path):
            self.app.save_file()

        with open(path) as fp:
            data = json.load(fp)
        # JSON serializes the tuple as a list; roundtrip equality holds.
        self.assertEqual(data["start_pos"], [7, 8])
        self.assertEqual(len(data["events"]), 2)

    def test_saved_macro_is_reopenable(self):
        import tempfile
        self.app.start_cursor_pos = (7, 8)
        self.app.events = [
            {"type": "rel", "dx": 1, "dy": 2, "time": 0.0},
            {"type": "scroll", "direction": "up", "clicks": 1, "time": 0.1},
        ]
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, 'macro.json')
        with patch('main.filedialog.asksaveasfilename', return_value=path):
            self.app.save_file()

        # Fresh app loads what the first one saved.
        app2 = make_app()
        with patch('main.filedialog.askopenfilename', return_value=path):
            app2.open_file()
        with app2.events_lock:
            self.assertEqual(len(app2.events), 2)
        self.assertEqual(app2.start_cursor_pos, (7, 8))


class TestHotkeyQueuePolling(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.app.toggle_record = MagicMock()
        self.app.handle_play_key = MagicMock()

    def test_poll_consumes_actions_in_order(self):
        self.app._ui_queue.put("rec")
        self.app._ui_queue.put("play")
        self.app._ui_queue.put("play_finished")
        self.app.btn_play = MagicMock()
        # Runs the real loop body; the trailing self.after() reschedule
        # fails on the bare instance and is swallowed by its own except.
        self.app._poll_hotkeys()
        self.app.toggle_record.assert_called_once()
        self.app.handle_play_key.assert_called_once()
        self.app.btn_play.configure.assert_called_once_with(
            text="\u25b6", fg_color="#388e3c")

    def test_poll_handles_empty_queue(self):
        # Must not raise even though the queue is empty.
        try:
            self.app._poll_hotkeys()
        except Exception as exc:
            self.fail(f"_poll_hotkeys raised with empty queue: {exc}")


if __name__ == '__main__':
    unittest.main()
