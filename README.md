# LinuxTask 🚀

A minimalist, high-performance macro recorder for Linux (X11 & Wayland), optimized for **Hyprland** and **CachyOS**. Inspired by TinyTask, built for Linux efficiency.

## Features
- **Global Hotkeys**: Record and Play from anywhere without focusing the app window.
- **Ultra Smooth Playback**: 100Hz sampling rate for natural cursor movement (no teleporting).
- **Wayland Native**: Works perfectly on Hyprland using `hyprctl` and `wlrctl`.
- **AFK/Loop Mode**: Repeat your macros infinitely for gaming or automation.
- **Customizable Keys**: Set your own Record and Play hotkeys.
- **Save/Load**: Export your macros to JSON files.

## Prerequisites
This tool requires `hyprctl` (native to Hyprland) and `wlrctl` (for clicks).

```bash
# Arch / CachyOS
sudo pacman -S wlrctl
```

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/JADRT22/LinuxTask.git
   cd LinuxTask
   ```
2. Setup environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install customtkinter evdev pynput
   ```
3. **Permissions (Crucial)**:
   LinuxTask needs to read input devices directly to work globally on Wayland. Add your user to the `input` group:
   ```bash
   sudo gpasswd -a $USER input
   sudo chmod 666 /dev/input/event*
   ```
   *(A reboot or relog is recommended after adding to the group).*

## Usage
Run the application:
```bash
python main.py
```
- **F8**: Start/Stop Recording
- **F9**: Start Playback
- **Emergency Stop**: Press **F8** anytime during playback to stop.

## License
MIT
