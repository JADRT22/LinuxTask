# Changelog

## [v2.2] - 2026-03-01
### 🛡️ Permissions & GNOME Wayland Compatibility
- **Hardware Access Automation:** Introduced `fix_linuxtask_perms.sh` to automate ACL and Udev configuration, allowing immediate hardware access without requiring a logout.
- **Pure Relative Movement Engine:** Implemented a new relative movement logic for GNOME Wayland users, bypassing security restrictions that blocked absolute coordinate capturing.
- **Ydotool Integration:** Optimized `ydotoold` daemon management, ensuring stable socket communication on Arch-based systems (CachyOS).
- **Coordinate Precision:** Fixed "drift" and "corner jump" bugs by implementing strict coordinate clamping and delta-based tracking.

## [v2.1] - 2026-02-22
### ⚡ Performance & Stability
- **Playback Engine Optimization:** Switched to direct subprocess calls for `hyprctl`, drastically reducing latency.
- **Improved Debugging:** Added terminal logging to track event count and UInput status.
- **Bug Fix:** Fixed a potential hang where playback would appear "stuck" due to shell overhead.

## [v2.0] - 2026-02-22
**Major Release: The "Anti-Bot" Update**

### ✨ New Features
- **🤖 Humanize Mode (Anti-Bot):**
    - New algorithm that adds micro-jitters (±2px) and random time delays (0-3%) to playback.
    - Makes macros virtually undetectable in games or anti-cheat systems.
    - Toggleable via the Settings menu.

### 🛠️ Improvements & Fixes
- **Settings UI Overhaul:**
    - Fixed "Black Screen" bug on Wayland/Hyprland by refactoring the settings window structure.
    - Improved contrast for buttons and text.
- **Stable Desktop Shortcut:**
    - Now consistently uses the system's `input-mouse` icon for better integration.
- **Codebase:**
    - Added unit tests (`test_jitter.py`) to ensure movement precision.
