# 🚀 LinuxTask
### *Ultimate Linux Macro Automation with Zero-Loss Global Capture*

[![GitHub Release](https://img.shields.io/github/v/release/JADRT22/LinuxTask?style=for-the-badge&color=BC8AD1)](https://github.com/JADRT22/LinuxTask/releases)
[![License](https://img.shields.io/github/license/JADRT22/LinuxTask?style=for-the-badge&color=8AB4D1)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/JADRT22/LinuxTask?style=for-the-badge&color=D1BD8A)](https://github.com/JADRT22/LinuxTask/stargazers)

**LinuxTask** is a high-performance, minimalist macro recorder optimized for Linux (X11 & Wayland). Inspired by TinyTask, it bypasses modern compositor security restrictions by reading directly from the kernel via `evdev`, ensuring hardware-level precision everywhere.

---

## ✨ Key Features (v2.2)

- **🛠️ GNOME Wayland Support:** Specialized driver using `ydotool` and relative movement logic for 100% compatibility with GNOME's security model.
- **⚡ Hardware-Level Capture:** Direct `evdev` integration for zero-loss global recording, even when the application is minimized.
- **🤖 Humanize (Anti-Bot):** Adds random jitter (±2px) and micro-time variations (0-3%) to mimic human behavior and avoid detection.
- **📟 Ultra-Compact UI:** Modern, distraction-free toolbar built with `customtkinter`.
- **󱄄 Global Hotkeys:** Control recording (F8) and playback (F9) from any application.
- **🛡️ Immediate Permissions:** Included `fix_linuxtask_perms.sh` script to grant hardware access instantly without reboots.

---

## 🛠️ Prerequisites

| Component | Package | Description |
| :--- | :--- | :--- |
| **Compositor** | `hyprland` / `gnome` | Optimized for Hyprland and GNOME Wayland. |
| **Input Engine** | `ydotool` | Required for cursor movement on GNOME Wayland. |
| **Python** | `python-evdev` | For global hardware event listening. |
| **UI Kit** | `customtkinter` | Modern dark-themed interface. |

---

## 🚀 Getting Started

### 1. Installation
Clone the repository and setup the virtual environment:
```bash
git clone https://github.com/JADRT22/LinuxTask.git
cd LinuxTask
python -m venv venv
source venv/bin/activate
pip install customtkinter evdev
```

### 2. Configure Permissions (Essential)
LinuxTask needs direct access to input devices. Run our automated fix script:
```bash
chmod +x fix_linuxtask_perms.sh
./fix_linuxtask_perms.sh
```
*This script configures the `input` group, `udev` rules, and applies immediate ACL permissions.*

### 3. Running the App
```bash
./run.sh
```
- **F8**: Toggle Recording (Global)
- **F9**: Toggle Playback / **Instant Stop** (Global)
- **⚙️ Icon**: Configure custom hotkeys and Humanize mode.

---

## 📂 Project Architecture
- `main.py`: Core application loop and event dispatcher.
- `drivers/`: Specialized modules for different desktop environments (GNOME, Hyprland).
- `fix_linuxtask_perms.sh`: Automation script for system-level configuration.

---
*Developed by JADRT22 - Optimized for Performance and Security.*
