# Contributing to LinuxTask

Thank you for your interest in contributing to LinuxTask! To maintain the quality and consistency of the project, please follow these guidelines.

## 🤝 Code of Conduct
We value professional, respectful, and productive interactions. Contributions should focus on technical excellence, performance, and clear architecture.

## 🛠️ Development Setup
1. **Clone the repository**: `git clone https://github.com/JADRT22/LinuxTask.git`
2. **Environment Setup**: Run `./tools/install.sh` to configure necessary permissions and dependencies.
3. **Dependencies**: Use a Python virtual environment (`venv`) to manage dependencies listed in `requirements.txt`.

## 📂 Repository Organization
- `src/`: Main application logic. All compositor drivers must inherit from `DesktopManager`.
- `tests/`: Unit and integration tests.
- `tools/`: Utility scripts for automation, installation, and deployment.
- `docs/`: Supplemental documentation and assets.

## 📜 Coding Standards
- **Python**: Adhere to **PEP 8** style guidelines. All functions and classes should include descriptive docstrings.
- **Shell**: Use `#!/usr/bin/env bash` and ensure scripts are compatible with `ShellCheck`.
- **Headers**: Every file must contain a standard header including License, Author, and a brief Description.
- **Naming**: Use clear and descriptive names (e.g., `event_handler` instead of `ev_h`).

## 🚀 Git Workflow
1. **Branching**: Create a branch with a descriptive name (e.g., `feat/new-driver` or `fix/crash-on-wayland`).
2. **Commits**: Use professional commit messages following the Conventional Commits pattern (e.g., `feat: add support for KDE` or `fix: resolve coordinate drift`).
3. **Tests**: Ensure all tests pass before submitting a Pull Request.

## ✅ Verification
You must verify your changes by running the existing test suite:
```bash
python3 -m unittest discover tests
```

---
*Maintained by JADRT22. Thank you for making LinuxTask better!*
