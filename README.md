# 🚀 LinuxTask
### *Ultimate Linux Macro Automation with Zero-Loss Global Capture*

[![GitHub Release](https://img.shields.io/github/v/release/JADRT22/LinuxTask?style=for-the-badge&color=BC8AD1)](https://github.com/JADRT22/LinuxTask/releases)
[![License](https://img.shields.io/github/license/JADRT22/LinuxTask?style=for-the-badge&color=8AB4D1)](docs/LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/JADRT22/LinuxTask?style=for-the-badge&color=D1BD8A)](https://github.com/JADRT22/LinuxTask/stargazers)

**LinuxTask** is a high-performance, minimalist macro recorder optimized for Linux (X11 & Wayland). It bypasses modern compositor security restrictions by reading directly from the kernel via `evdev`, ensuring hardware-level precision everywhere.

---

## ✨ Key Features

- **🛠️ GNOME Wayland Support:** Specialized driver using `ydotool` and relative movement logic for 100% compatibility with GNOME's security model.
- **⚡ Hardware-Level Capture:** Direct `evdev` integration for zero-loss global recording, even when the application is minimized.
- **🤖 Humanize (Anti-Bot):** Adds random jitter (±2px) and micro-time variations (0-3%) to mimic human behavior and avoid detection.
- **📟 Ultra-Compact UI:** Modern, distraction-free toolbar built with `customtkinter`.
- **󱄄 Global Hotkeys:** Control recording and playback from any application.
- **🛡️ Immediate Permissions:** Integrated automation to grant hardware access instantly.

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
