# -*- coding: utf-8 -*-
"""
LinuxTask - test_cli.py
Description: Headless tests for the `play` CLI (issue #5): macro loading
             and validation, argument parsing, the process exit codes, and
             that headless playback dispatches through the same Playback
             code the GUI uses. No display or hardware required.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import cli  # noqa: E402
import main  # noqa: E402  (imports customtkinter, but no display touched)
from evdev import ecodes as e  # noqa: E402


class MacroFileMixin(unittest.TestCase):
    """Helpers to write a macro JSON into a temp file."""

    def make_file(self, payload):
        fd, path = tempfile.mkstemp(suffix=".json")
        self.addCleanup(os.unlink, path)
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(payload, fp)
        return path


class TestParser(unittest.TestCase):

    def test_play_defaults(self):
        args = cli.build_parser().parse_args(["play", "m.json"])
        self.assertEqual(args.file, "m.json")
        self.assertEqual(args.speed, 1.0)
        self.assertFalse(args.loop)
        self.assertFalse(args.humanize)

    def test_play_flags(self):
        args = cli.build_parser().parse_args(
            ["play", "m.json", "--speed", "2.5", "--loop", "--humanize"])
        self.assertEqual(args.speed, 2.5)
        self.assertTrue(args.loop)
        self.assertTrue(args.humanize)
        self.assertIs(args.func, cli.run_play)

    def test_start_pos_parses_a_point(self):
        args = cli.build_parser().parse_args(
            ["play", "m.json", "--start-pos", "400,300"])
        self.assertEqual(args.start_pos, (400, 300))

    def test_start_pos_defaults_to_none(self):
        args = cli.build_parser().parse_args(["play", "m.json"])
        self.assertIsNone(args.start_pos)

    def test_start_pos_rejects_garbage(self):
        with self.assertRaises(SystemExit) as cm, \
                contextlib.redirect_stderr(io.StringIO()):
            cli.build_parser().parse_args(
                ["play", "m.json", "--start-pos", "abc"])
        self.assertEqual(cm.exception.code, 2)

    def test_a_subcommand_is_required(self):
        with self.assertRaises(SystemExit) as cm:
            cli.build_parser().parse_args([])
        self.assertEqual(cm.exception.code, 2)


class TestLoad(MacroFileMixin):
    """The headless loader must validate exactly like Playback.open_file."""

    def test_loads_events_and_start_pos(self):
        path = self.make_file({
            "start_pos": [10, 20],
            "events": [{"type": "rel", "dx": 5, "dy": -5, "time": 0.0}],
        })
        player = cli.HeadlessPlayer()
        self.assertEqual(player.load(path), 1)
        self.assertEqual(player.start_cursor_pos, (10, 20))

    def test_legacy_bare_list_is_accepted(self):
        path = self.make_file([{"type": "key", "code": 30, "val": 1}])
        player = cli.HeadlessPlayer()
        self.assertEqual(player.load(path), 1)
        self.assertIsNone(player.start_cursor_pos)

    def test_invalid_events_are_filtered_not_fatal(self):
        path = self.make_file({
            "events": [
                {"type": "rel", "dx": 1, "dy": 1, "time": 0.0},
                {"type": "nonsense"},
                "not-a-dict",
                {"type": "key", "code": "A", "val": 1},
            ],
        })
        player = cli.HeadlessPlayer()
        with self.assertLogs("LinuxTask", level="WARNING") as logs:
            self.assertEqual(player.load(path), 1)
        self.assertTrue(any("Filtered" in m for m in logs.output))

    def test_malformed_start_pos_is_dropped(self):
        path = self.make_file({
            "start_pos": ["a", "b"],
            "events": [{"type": "rel", "dx": 1, "dy": 1, "time": 0.0}],
        })
        player = cli.HeadlessPlayer()
        player.load(path)
        self.assertIsNone(player.start_cursor_pos)

    def test_non_list_events_raise(self):
        path = self.make_file({"events": {"type": "rel"}})
        with self.assertRaises(ValueError):
            cli.HeadlessPlayer().load(path)


class TestRunPlay(MacroFileMixin):
    """Exit codes and dispatch of the `play` subcommand."""

    def test_missing_file_exits_2_without_touching_the_driver(self):
        # A bad path must not initialize a compositor driver (on KDE
        # Wayland that would open the portal authorization dialog).
        with patch.object(cli, "AutoDetectDriver") as factory, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["play", "/nope/missing.json"]), 2)
        factory.assert_not_called()

    def test_macro_without_valid_events_exits_2(self):
        path = self.make_file({"events": [{"type": "junk"}]})
        with patch.object(cli, "AutoDetectDriver") as factory, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["play", path]), 2)
        factory.assert_not_called()

    def test_non_positive_speed_exits_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["play", "x.json", "--speed", "0"]), 2)

    def test_unsupported_desktop_exits_1(self):
        path = self.make_file({"events": [{"type": "rel", "dx": 1, "dy": 1}]})
        err = io.StringIO()
        with patch.object(cli, "AutoDetectDriver",
                          side_effect=RuntimeError("Unsupported desktop")), \
                contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(["play", path]), 1)
        self.assertIn("Unsupported desktop", err.getvalue())

    def test_playback_dispatches_through_playback_thread(self):
        path = self.make_file({
            "start_pos": [100, 200],
            "events": [
                {"type": "pos", "x": 300, "y": 400, "time": 0.0},
                {"type": "rel", "dx": 5, "dy": -5, "time": 0.0},
                {"type": "scroll", "direction": "down", "clicks": 2,
                 "time": 0.0},
                {"type": "key", "code": e.KEY_A, "val": 1, "time": 0.0},
                {"type": "key", "code": e.BTN_LEFT, "val": 1, "time": 0.0},
            ],
        })
        manager = MagicMock()
        manager.move_relative.return_value = True
        manager.mouse_button.return_value = True
        manager.scroll.return_value = True
        uinput = MagicMock()
        with patch.object(cli, "AutoDetectDriver", return_value=manager), \
                patch.object(cli, "_create_uinput", return_value=uinput):
            self.assertEqual(cli.main(["play", path]), 0)

        manager.move_cursor.assert_any_call(100, 200)   # start_pos warp
        manager.move_cursor.assert_any_call(300, 400)   # pos event
        manager.move_relative.assert_called_once_with(5, -5)
        manager.scroll.assert_called_once_with("down", 2)
        manager.mouse_button.assert_called_once_with(e.BTN_LEFT, True)
        # Keyboard always goes through uinput, driver or not.
        self.assertIn((e.EV_KEY, e.KEY_A, 1),
                      [c.args for c in uinput.write.call_args_list])
        uinput.close.assert_called_once()

    def test_speed_and_flags_reach_the_player(self):
        path = self.make_file({"events": [{"type": "rel", "dx": 1, "dy": 1}]})
        manager = MagicMock()
        captured = {}

        class Spy(cli.HeadlessPlayer):
            def play(self):
                captured["speed"] = self.speed_var.get()
                captured["loop"] = self.loop_enabled
                captured["humanize"] = self.humanize_enabled.get()
                captured["start_pos"] = self.start_cursor_pos

        with patch.object(cli, "AutoDetectDriver", return_value=manager), \
                patch.object(cli, "_create_uinput", return_value=None), \
                patch.object(cli, "HeadlessPlayer", Spy):
            self.assertEqual(
                cli.main(["play", path, "--speed", "4", "--loop",
                          "--humanize", "--start-pos", "12,34"]), 0)
        self.assertEqual(captured, {"speed": "4.0", "loop": True,
                                    "humanize": True, "start_pos": (12, 34)})

    def test_start_pos_overrides_the_macro_value(self):
        # A macro recorded on a desktop that cannot read the cursor carries
        # no start_pos, and one recorded elsewhere carries its own;
        # --start-pos must win in both cases.
        path = self.make_file({
            "start_pos": [10, 20],
            "events": [{"type": "rel", "dx": 1, "dy": 1}],
        })
        captured = {}

        class Spy(cli.HeadlessPlayer):
            def play(self):
                captured["start_pos"] = self.start_cursor_pos

        with patch.object(cli, "AutoDetectDriver", return_value=MagicMock()), \
                patch.object(cli, "_create_uinput", return_value=None), \
                patch.object(cli, "HeadlessPlayer", Spy):
            self.assertEqual(
                cli.main(["play", path, "--start-pos", "7,8"]), 0)
        self.assertEqual(captured["start_pos"], (7, 8))

    def test_macro_start_pos_is_used_without_the_flag(self):
        path = self.make_file({
            "start_pos": [10, 20],
            "events": [{"type": "rel", "dx": 1, "dy": 1}],
        })
        captured = {}

        class Spy(cli.HeadlessPlayer):
            def play(self):
                captured["start_pos"] = self.start_cursor_pos

        with patch.object(cli, "AutoDetectDriver", return_value=MagicMock()), \
                patch.object(cli, "_create_uinput", return_value=None), \
                patch.object(cli, "HeadlessPlayer", Spy):
            self.assertEqual(cli.main(["play", path]), 0)
        self.assertEqual(captured["start_pos"], (10, 20))

    def test_uinput_unavailable_is_not_fatal(self):
        path = self.make_file({"events": [{"type": "key", "code": e.KEY_A,
                                           "val": 1, "time": 0.0}]})
        with patch.object(cli, "AutoDetectDriver", return_value=MagicMock()), \
                patch.object(cli, "_create_uinput", return_value=None):
            self.assertEqual(cli.main(["play", path]), 0)


class TestMainDispatch(unittest.TestCase):
    """main.py must route `play` to the CLI and everything else to the GUI."""

    def test_play_is_handed_to_the_cli(self):
        with patch.object(cli, "main", return_value=0) as cli_main:
            self.assertEqual(main.main(["play", "m.json"]), 0)
        cli_main.assert_called_once_with(["play", "m.json"])

    def test_help_is_handed_to_the_cli(self):
        with patch.object(cli, "main", return_value=0) as cli_main:
            main.main(["--help"])
        cli_main.assert_called_once_with(["--help"])

    def test_no_arguments_starts_the_gui(self):
        with patch.object(main, "LinuxTaskApp") as app_cls:
            main.main([])
        app_cls.return_value.mainloop.assert_called_once()


if __name__ == '__main__':
    unittest.main()
