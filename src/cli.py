# -*- coding: utf-8 -*-
"""
LinuxTask - cli.py
Description: Headless command-line interface (issue #5). Replays a macro
             JSON file without starting the GUI, so a script can drive
             input. Reuses Playback.playback_thread verbatim — only the
             window-owned attributes it reads are provided here (see
             HeadlessPlayer), so the CLI replays through exactly the same
             code path the toolbar uses.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import argparse
import json
import logging
import queue
import sys
import threading

import evdev
from evdev import ecodes as e

from drivers.factory import AutoDetectDriver
from recorder import VIRTUAL_DEVICE_NAME
from playback import Playback

logger = logging.getLogger("LinuxTask")


class _Value:
    """Stand-in for a Tk variable: exposes the .get() the replay path reads."""

    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class HeadlessPlayer(Playback):
    """Replays a macro with no GUI.

    `Playback.playback_thread` reads a handful of attributes the window
    normally owns (speed/humanize Tk variables, the loop flag, the UI
    queue). They are provided here as plain values, so the replay logic
    itself stays untouched and shared with the GUI.
    """

    def __init__(self, manager=None, speed=1.0, loop=False, humanize=False):
        # manager may stay None while the macro file is validated, so a
        # bad file fails fast without initializing a compositor driver
        # (on KDE Wayland that opens the portal authorization dialog).
        self.manager = manager
        self.uinput_device = None
        self.events = []
        self.events_lock = threading.Lock()
        self.playing = False
        self.loop_enabled = loop
        self.start_cursor_pos = None
        self.speed_var = _Value("%s" % speed)
        self.humanize_enabled = _Value(bool(humanize))
        # playback_thread reports completion and driver skips here; the
        # CLI has no event loop, so nothing consumes it.
        self._ui_queue = queue.Queue()

    def load(self, path):
        """Loads a macro JSON; returns how many events were accepted.

        Mirrors Playback.open_file's validation (the same _validate_event
        keeps the two paths honest) but without the file dialog, which
        needs a display.
        """
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        start_pos = None
        if isinstance(data, dict):
            raw_events = data.get("events", [])
            pos = data.get("start_pos")
            if (isinstance(pos, (list, tuple)) and len(pos) == 2
                    and all(isinstance(v, (int, float))
                            and not isinstance(v, bool) for v in pos)):
                start_pos = tuple(pos)
        else:
            raw_events = data
        if not isinstance(raw_events, list):
            raise ValueError("events must be a list")
        valid = [ev for ev in raw_events if self._validate_event(ev)]
        if len(valid) != len(raw_events):
            logger.warning("Filtered %d invalid event(s) from macro.",
                           len(raw_events) - len(valid))
        self.events = valid
        self.start_cursor_pos = start_pos
        return len(valid)

    def play(self):
        """Runs one (or, with --loop, repeated) pass, blocking."""
        self.playing = True
        self.playback_thread()


def _point(text):
    """argparse type: 'X,Y' -> (int, int)."""
    try:
        xs, ys = text.split(",")
        return (int(xs), int(ys))
    except ValueError:
        raise argparse.ArgumentTypeError(
            "expected 'X,Y' in screen pixels, e.g. 400,300")


def _create_uinput():
    """Creates the virtual replay device; None when it is unavailable."""
    try:
        return evdev.UInput(
            {
                e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE]
                + list(range(1, 512)),
                e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL],
            },
            name=VIRTUAL_DEVICE_NAME, vendor=0x1234, product=0x5678,
        )
    except (PermissionError, OSError) as exc:
        logger.warning(
            "UInput unavailable (%s): keyboard replay and the driver "
            "fallbacks are disabled. Re-run ./tools/install.sh.", exc)
        return None


def run_play(args):
    """Executes `play <macro.json>`. Returns the process exit code."""
    if args.speed <= 0:
        print("linuxtask: --speed must be greater than 0", file=sys.stderr)
        return 2

    player = HeadlessPlayer(
        speed=args.speed, loop=args.loop, humanize=args.humanize)
    try:
        count = player.load(args.file)
    except (OSError, ValueError) as exc:
        print("linuxtask: cannot read macro '%s': %s" % (args.file, exc),
              file=sys.stderr)
        return 2
    if count == 0:
        print("linuxtask: macro '%s' has no valid events" % args.file,
              file=sys.stderr)
        return 2

    if args.start_pos is not None:
        # Overrides the macro's own start_pos: on desktops that cannot
        # read the cursor, a relative macro only repeats when it
        # starts where it started before.
        player.start_cursor_pos = args.start_pos

    # Only now touch the compositor: a bad file must not open a portal
    # authorization dialog or need input permissions.
    player.manager = AutoDetectDriver()
    # Portal drivers (KDE Wayland) report skipped input through
    # warn_fn — a dialog in the GUI, a log line here.
    if hasattr(player.manager, "warn_fn"):
        player.manager.warn_fn = lambda msg: logger.warning("driver: %s", msg)

    player.uinput_device = _create_uinput()
    logger.info("Playing %s: %d events at %sx%s%s", args.file, count,
                args.speed, ", loop" if args.loop else "",
                ", humanize" if args.humanize else "")
    if args.loop:
        print("Looping — press Ctrl+C to stop.", file=sys.stderr)
    try:
        player.play()
    except KeyboardInterrupt:
        player.playing = False
        print("Stopped.", file=sys.stderr)
        return 130
    finally:
        if player.uinput_device is not None:
            try:
                player.uinput_device.close()
            except Exception:
                logger.debug("Failed to close UInput device.", exc_info=True)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="linuxtask",
        description="LinuxTask headless CLI — replay a recorded macro "
                    "without opening the GUI.")
    sub = parser.add_subparsers(dest="command", required=True)

    play = sub.add_parser(
        "play", help="replay a macro JSON file (as saved by the GUI)")
    play.add_argument("file", help="macro JSON file")
    play.add_argument(
        "--speed", type=float, default=1.0,
        help="playback speed multiplier (default 1.0; the GUI offers 0.5-10)")
    play.add_argument(
        "--start-pos", type=_point, metavar="X,Y", default=None,
        help="move the cursor to X,Y before replaying, overriding the "
             "macro's stored start position (the way to repeat a relative "
             "macro on a desktop that cannot read the cursor)")
    play.add_argument(
        "--loop", action="store_true", help="keep replaying until Ctrl+C")
    play.add_argument(
        "--humanize", action="store_true",
        help="add +/-2px jitter and 0-3%% timing variance")
    play.add_argument("-v", "--verbose", action="store_true",
                      help="debug logging")
    play.set_defaults(func=run_play)
    return parser


def main(argv=None):
    """CLI entry point. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False)
        else logging.INFO,
        format="[%(levelname)s] %(name)s: %(message)s")
    try:
        return args.func(args)
    except RuntimeError as exc:
        # Unsupported desktop / missing driver dependency: the factory
        # raises with install instructions, which must reach the user.
        print("linuxtask: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
