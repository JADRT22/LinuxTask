# Contributing to LinuxTask

Thank you for considering contributing to LinuxTask! To maintain high standards of code quality and repository organization, please follow these guidelines.

## 🥒 The Prime Directive
**No Slop.** We value precision, performance, and clean architecture. If your code looks like a Jerry wrote it, it will be rejected.

## 🛠️ Development Environment
1. Clone the repository.
2. Run `./tools/install.sh` to setup the environment and permissions.
3. Use a virtual environment (`venv`) for Python dependencies.

## 📂 Repository Structure
- `src/`: All source code. Drivers must inherit from `DesktopManager`.
- `tests/`: All tests. We use `unittest` and `pytest`.
- `tools/`: Automation and utility scripts.
- `docs/`: Extra documentation and assets.

## 📜 Coding Standards
- Follow **PEP 8** for all Python code.
- Every file must have a standard header (License, Author, Description).
- Use clear, descriptive variable names. No `temp1`, `data2`, etc.
- Document complex logic with concise comments.

## 🚀 Git Workflow
1. Create a descriptive branch: `feature/your-feature` or `fix/your-bug`.
2. Commit with professional messages: `Epic: Add support for X` or `Fix: Resolve issue with Y`.
3. Ensure all tests pass before submitting a Pull Request.

## ✅ Verification
Run the tests before submitting changes:
```bash
python3 -m unittest discover tests
```

*Be a Rick, not a Jerry. Happy coding!*
