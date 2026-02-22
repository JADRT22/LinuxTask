# Changelog

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
