# Security Policy

Thanks for taking the time to report a vulnerability. LinuxTask is a
small project, and this page describes what is realistically in scope and
what happens with a report.

## Reporting a vulnerability

Use GitHub's private disclosure channel: [Report a security
vulnerability](https://github.com/JADRT22/LinuxTask/security/advisories/new).
The report is visible only to you and the maintainers until it is
published, so a fix can land before the issue becomes public.

Please do not open a normal issue for anything exploitable. Ordinary
bugs — a macro that replays wrong, a driver that fails to detect a
monitor — belong in [Issues](https://github.com/JADRT22/LinuxTask/issues).

There is no bug bounty and no fixed response SLA. Expect an acknowledgement
within a few days; the maintainer answers in their spare time.

## What LinuxTask is, for the sake of the threat model

- Recording reads raw events from `/dev/input/event*` through `evdev`.
  It sees every keystroke made while a recording is armed, system-wide,
  including passwords typed in another window. That is inherent to
  keyboard recording, not a flaw to report — the app warns before the
  first recording, and the warning can be silenced.
- Replay writes through `/dev/uinput` (a virtual device) or the
  compositor's own APIs. The `udev` rule grants **read-only** access to
  the physical devices and read/write only to `/dev/uinput`, which is
  why installing the app needs sudo.
- Macro files are data, not code: they are parsed and replayed, never
  `eval`'d. A malicious macro can still replay arbitrary keystrokes, in
  the same way a `.xdotool` script can; treat macro JSON you did not
  record as you would any executable.
- On KDE Wayland the driver talks to KWin over D-Bus and to the XDG
  RemoteDesktop portal; on GNOME it talks to a bundled Shell extension.
  Replies are checked against the expected bus name's sender, and the
  extension verifies the caller's UID.

## In scope

- Reading another user's or process's input, or injecting input into a
  session the app does not own, through a defect in the app.
- Trusting a D-Bus/portal/extension reply it should not have trusted,
  including the RemoteDesktop session negotiation and the KWin cursor
  probe.
- Path traversal or arbitrary file write through macro files,
  recordings, `--start-pos`, the settings file or import/export.
- Command injection through compositor IPC (`hyprctl`, `swaymsg`,
  `xdotool`, `ydotool`, `gdbus`, `kscreen-doctor`, `xrandr`) or through
  values returned by those commands.
- A crash reachable from a normal macro or config file that leaves the
  session in an unusable state (for example an armed recording that
  cannot be stopped).
- Credential or secret leakage into logs, saved macros or crash output.

## Out of scope

- Anything requiring the attacker to already run code as your user, or
  to be a member of the `input` group / able to open `/dev/uinput`.
  Processes with that access can already read or inject input at the
  kernel level; the app does not defend against it and cannot.
- Abuse of the app by its own user (recording someone else's keyboard,
  macros used for spam). Legitimate concern, not a vulnerability.
- Vulnerabilities in the compositor, the distro packages, or upstream
  dependencies (report those upstream; keeping dependencies patched is
  covered by Dependabot).
- Prompt-injection style issues in AI-assisted contributions, and
  anything about the GitHub repository itself rather than the software.

## Version support

Only the current release (`main` plus the latest tagged version) receives
security fixes. There is no backport branch.
