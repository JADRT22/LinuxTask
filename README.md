# 🚀 LinuxTask
### *Ultimate Linux Macro Automation with Zero-Loss Global Capture*

[![GitHub Release](https://img.shields.io/github/v/release/JADRT22/LinuxTask?style=for-the-badge&color=BC8AD1)](https://github.com/JADRT22/LinuxTask/releases)
[![License](https://img.shields.io/github/license/JADRT22/LinuxTask?style=for-the-badge&color=8AB4D1)](docs/LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/JADRT22/LinuxTask?style=for-the-badge&color=D1BD8A)](https://github.com/JADRT22/LinuxTask/stargazers)

**LinuxTask** is a high-performance, minimalist macro recorder optimized for Linux (X11 & Wayland). It bypasses modern compositor security restrictions by reading directly from the kernel via `evdev`, ensuring hardware-level precision everywhere.

---

## ✨ Key Features

- **🖥️ X11 Support (New!)**: Specialized driver for Cinnamon, MATE, XFCE, and other X11-based environments using `xdotool`.
- **🛠️ GNOME Wayland Support**: Specialist driver with relative movement logic for 100% compatibility with Wayland security models.
- **⚡ Hardware-Level Capture**: Direct `evdev` integration for zero-loss global recording of keys and mouse (including scroll wheel).
- **🤖 Humanize (Anti-Bot)**: Adds random jitter (±2px) and micro-time variations to mimic human behavior.
- **📟 Ultra-Compact UI**: Modern, distraction-free toolbar with dark theme by default.
- **󱄄 Global Hotkeys**: F8 to Record, F9 to Play (configurable, with ESC to cancel).

---

## 🛠️ Prerequisites

| Component | Package | Description |
| :--- | :--- | :--- |
| **Compositor** | `hyprland` / `gnome` / `cinnamon` | Support for X11, GNOME Wayland, and Hyprland. |
| **Movement Engine** | `xdotool` / `ydotool` | Required for cursor control (X11 / GNOME Wayland). |
| **Python** | `python-evdev` | For global hardware event listening. |
| **UI Kit** | `customtkinter` | Modern dark-themed interface. |

---

## 🚀 Getting Started

### 1. Installation
Clone the repository and setup the environment:
```bash
git clone https://github.com/JADRT22/LinuxTask.git
cd LinuxTask
./tools/install.sh
```

### 2. Running the App
```bash
./run.sh
```
- **Hotkeys**: Configure your preferred keys in the settings menu (⚙️).
- **Loop**: Enable continuous playback with the 🔁 button.

---

## 📂 Project Architecture

The project is organized into a professional directory structure:

- `src/`: Core application logic and desktop drivers.
- `tests/`: Unit and integration tests.
- `docs/`: Documentation, licenses, and changelogs.
- `tools/`: Utility scripts for installation, execution, and releases.
- `assets/`: Icons and visual resources.

---
*Developed by JADRT22 - Optimized for Performance and Security.*
