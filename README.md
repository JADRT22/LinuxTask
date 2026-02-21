# 🚀 LinuxTask
### *Desktop Macro Automation with Zero-Loss Global Capture*

[![GitHub Release](https://img.shields.io/github/v/release/JADRT22/LinuxTask?style=for-the-badge&color=BC8AD1)](https://github.com/JADRT22/LinuxTask/releases)
[![License](https://img.shields.io/github/license/JADRT22/LinuxTask?style=for-the-badge&color=8AB4D1)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/JADRT22/LinuxTask?style=for-the-badge&color=D1BD8A)](https://github.com/JADRT22/LinuxTask/stargazers)

**A minimalist, high-performance macro recorder for Linux (X11 & Wayland), optimized for Hyprland and CachyOS. Inspired by TinyTask, built for absolute precision.**

---

## 💡 Why LinuxTask?

Recording macros on Wayland has always been a challenge due to security restrictions. **LinuxTask** bypasses these limitations by reading directly from the kernel hardware via `evdev`, ensuring **Zero-Loss Global Capture**. Whether you're farming AFK in games like Roblox or automating boring desktop tasks, LinuxTask works everywhere, even when minimized.

It features **Ultra-Smooth Playback** at 100Hz, mimicking human mouse movements perfectly instead of "teleporting" the cursor.

---

## ✨ Key Features
- **󱄄 Global Hotkey Control:** Start/Stop recording and playback from any window (default F8/F9).
- **󰕮 Absolute Precision:** Uses `hyprctl` for pixel-perfect coordinate movement on Hyprland.
- **󰸉 Smooth Sampling:** 100Hz sampling rate for natural, fluid mouse paths.
- **🔁 Infinite Loop Mode:** Perfect for AFK farming or repetitive data entry.
- **⚙️ Customizable Hotkeys:** Remap Record and Play keys directly from the UI to any key on your keyboard.
- **💾 Save & Load:** Export your best macros to JSON and share them or back them up.

---

## 🛠️ Prerequisites & Dependencies

To ensure full functionality on Wayland/Hyprland, install these components:

| Component | Package | Description |
| :--- | :--- | :--- |
| **Input Tool** | `wlrctl` | Handles virtual pointer clicks. |
| **Compositor** | `hyprland` | Required for `hyprctl` absolute positioning. |
| **Python** | `python-evdev` | For global hardware event listening. |
| **UI Kit** | `customtkinter` | Modern dark-themed interface. |

---

## 🚀 Getting Started

### 1. Installation
Clone the repository and setup the environment:
```bash
git clone https://github.com/JADRT22/LinuxTask.git
cd LinuxTask
python -m venv venv
source venv/bin/activate
pip install customtkinter evdev pynput
```

### 2. Permissions (Essential)
LinuxTask needs permission to read input devices directly. Run these commands:
```bash
sudo gpasswd -a $USER input
sudo chmod 666 /dev/input/event*
```
*Note: A logout/login is recommended after adding your user to the `input` group.*

### 3. Usage
Run the app and use the global hotkeys:
```bash
./run.sh
```
- **F8**: Toggle Recording (Global)
- **F9**: Toggle Playback (Global)
- **F8 (during play)**: Emergency Stop

---

## 📂 Architecture
- `main.py`: The core application logic using `evdev` for capture and `hyprctl` for playback.
- `run.sh`: Streamlined launcher that handles the virtual environment.
- `linuxtask.desktop`: Menu entry for your application launcher (Rofi/Drun).

---
*Developed by JADRT22 - Optimized for Hyprland*
