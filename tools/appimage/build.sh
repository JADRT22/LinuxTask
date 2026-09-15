#!/usr/bin/env bash
# Builds LinuxTask-x86_64.AppImage from the current source tree.
#
# Why the label patch? The AppImage bundles python-build-standalone,
# whose Tk is compiled WITHOUT Xft/fontconfig -- it only knows the
# "fixed" bitmap font. Non-ASCII toolbar glyphs (which render fine on
# distro installs via DejaVu Sans) would show as tofu boxes, so the
# staged copy gets ASCII text labels instead.
#
# Usage: ./tools/appimage/build.sh
# Requirements: uv (or a python with the `appimage` PyPI package),
#   appimagetool (auto-downloaded by the build tool if missing).
# Output: build/appimage/dist/LinuxTask-x86_64.AppImage

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)"
STAGE="$REPO_ROOT/build/appimage"
PROJ="$STAGE/proj"
export PROJ

rm -rf "$PROJ"
mkdir -p "$PROJ"
cp -r "$REPO_ROOT/src/drivers" "$PROJ/"
rm -rf "$PROJ/drivers/__pycache__"
cp "$REPO_ROOT/src/main.py" "$PROJ/linuxtask_main.py"
cp "$REPO_ROOT/assets/icon.png" "$PROJ/"
cp "$REPO_ROOT/tools/appimage/pyproject.toml" "$PROJ/"
cp "$REPO_ROOT/tools/appimage/LinuxTask.desktop" "$PROJ/"

# Entry point: main.py defines main() directly (used by the
# linuxtask console script via pyproject.toml).
python3 - <<'EOF'
import os
p = os.path.join(os.environ["PROJ"], "linuxtask_main.py")
src = open(p).read()
# ASCII toolbar labels (bundled Tk has no symbol fonts).
subs = [
    ('("●",', '("REC",'),
    ('("▶",', '("PLAY",'),
    ('("↻",', '("LOOP",'),
    ('text="⚙"', 'text="SET"'),
    ('text="▶"', 'text="PLAY"'),
    ('text="■"', 'text="STOP"'),
    ('text="●"', 'text="REC"'),
]
for old, new in subs:
    assert old in src, f"pattern not found: {old}"
    src = src.replace(old, new)
# Text labels need a smaller font to fit the 40px buttons.
src = src.replace(
    'self.btns[1].configure(font=("DejaVu Sans", 11))',
    'self.btns[1].configure(font=("DejaVu Sans", 11))\n'
    '        for b in self.btns[2:5]:\n'
    '            b.configure(font=("DejaVu Sans", 10))',
)
open(p, "w").write(src)
print("staged + patched OK")
EOF

echo "--- build tool (isolated env) ---"
if ! python3 -c "import appimage" 2>/dev/null; then
    uv venv "$STAGE/build-env" >/dev/null
    uv pip install --python "$STAGE/build-env/bin/python" appimage >/dev/null
fi
BPY="$STAGE/build-env/bin/python"
[ -x "$BPY" ] || BPY="python3"

echo "--- building (downloads toolchain on first run) ---"
(
    cd "$PROJ"
    "$BPY" -m appimage.ctl build
)
echo "--- done: $PROJ/dist/LinuxTask-x86_64.AppImage ---"
