#!/usr/bin/env bash
# Builds LinuxTask-x86_64.AppImage from the current source tree.
#
# Why the label patch? The AppImage bundles python-build-standalone,
# whose Tk is compiled WITHOUT Xft/fontconfig -- it only knows the
# "fixed" bitmap font. Non-ASCII toolbar glyphs (which render fine on
# distro installs via DejaVu Sans) would show as tofu boxes, so the
# staged copy gets ASCII text labels instead.
#
# NEW build-time host requirements (for the KDE Wayland D-Bus stack):
# the bundle needs `dbus` (dbus-python) and `gi` (PyGObject), which PyPI
# does not ship as cp312 glibc wheels, so build.sh source-builds them
# against the exact bundled interpreter. That needs: pkg-config plus the
# headers/dbus, glib2, gobject-introspection, cairo (Arch package names;
# on other distros the -dev/-devel equivalents), and meson/ninja (pip,
# into the scratch wheel-env, not the system). Their RUNTIME shared
# libraries (libdbus-1.so.3, libglib, libgirepository) and typelibs are
# deliberately NOT bundled: every KDE host already ships them.
#
# Usage: ./tools/appimage/build.sh
# Requirements: uv (or a python with the `appimage` PyPI package),
#   appimagetool (auto-downloaded by the build tool if missing),
#   curl, plus the build-time host packages listed above.
# Output: build/appimage/dist/LinuxTask-x86_64.AppImage

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)"
STAGE="$REPO_ROOT/build/appimage"
PROJ="$STAGE/proj"
WHEELS="$STAGE/wheels"
# python-build-standalone tarball, cached OUTSIDE proj/ (staging wipes
# proj/ every run) and handed to appimage.ctl via --python-archive so
# the tool installs the exact same interpreter the wheels target.
PYTARBALL="$STAGE/python-3.12-latest.tar.gz"
export PROJ

rm -rf "$PROJ"
mkdir -p "$PROJ"
cp -r "$REPO_ROOT/src/drivers" "$PROJ/"
rm -rf "$PROJ/drivers/__pycache__"
cp "$REPO_ROOT/src/main.py" "$PROJ/linuxtask_main.py"
# v3.1 split main.py into recorder.py/playback.py; the bundle needs
# them alongside linuxtask_main.py or every launch dies at import
# (ModuleNotFoundError: recorder).
cp "$REPO_ROOT/src/recorder.py" "$PROJ/recorder.py"
cp "$REPO_ROOT/src/playback.py" "$PROJ/playback.py"
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
# Text labels need a smaller font to fit the 32px buttons.
old_font = 'self.btns[1].configure(font=("DejaVu Sans", 10))'
assert old_font in src, f"pattern not found: {old_font}"
src = src.replace(
    old_font,
    'self.btns[1].configure(font=("DejaVu Sans", 10))\n'
    '        for b in self.btns[2:5]:\n'
    '            b.configure(font=("DejaVu Sans", 10))',
)
open(p, "w").write(src)
print("staged + patched OK")
EOF

# --- bundled-Python tarball (ABI source for the wheels) ---------------
# Source-built wheels must target the exact ABI of the bundled
# python-build-standalone build ([tool.appimage] python = "3.12"), so
# the same tarball that feeds the AppDir interpreter is resolved here
# (same asset rule as appimage/ctl/_python.py) and reused for both.
if [ ! -f "$PYTARBALL" ]; then
    echo "--- resolving python-build-standalone 3.12 tarball ---"
    ASSET_URL="$(python3 - <<'EOF'
import json, urllib.request
data = json.load(urllib.request.urlopen(
    "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"))
for a in data["assets"]:
    u = a["browser_download_url"]
    if ("cpython-3.12." in u
            and "x86_64-unknown-linux-gnu-install_only_stripped" in u
            and "freethreaded" not in u):
        print(u)
        break
EOF
)"
    [ -n "$ASSET_URL" ] || {
        echo "ERROR: no cpython-3.12 x86_64 install_only_stripped asset found upstream." >&2
        exit 1
    }
    curl -fL --retry 3 --continue-at - -o "$PYTARBALL.tmp" "$ASSET_URL"
    # Atomic publish: only complete downloads replace the cache entry,
    # so an interrupted curl can never leave a truncated tarball that
    # the cache-then-skip logic below would trust forever.
    mv "$PYTARBALL.tmp" "$PYTARBALL"
fi

# --- build-time host dependency check (fail fast, actionable) --------
if ! command -v pkg-config >/dev/null 2>&1; then
    echo "ERROR: pkg-config not found. It is required to source-build the dbus-python/PyGObject wheels (see header comment)." >&2
    exit 1
fi
missing_pc=""
for pc in dbus-1 gobject-introspection-1.0 glib-2.0; do
    pkg-config --exists "$pc" || missing_pc="$missing_pc $pc"
done
if [ -n "$missing_pc" ]; then
    cat >&2 <<MSG
ERROR: pkg-config cannot find:$missing_pc
The dbus-python/PyGObject wheels are source-built for the bundled
cp312 interpreter and need those headers at build time. On Arch:
  pacman -S dbus glib2 gobject-introspection cairo pkg-config
(other distros: -dev/-devel packages of dbus, glib2,
gobject-introspection and cairo).
MSG
    exit 1
fi

# --- dbus/PyGObject/pycairo wheels, built by the bundled ABI ---------
PYWHEEL="$STAGE/wheel-env"
if [ ! -x "$PYWHEEL/bin/python3" ]; then
    rm -rf "$PYWHEEL"
    mkdir -p "$PYWHEEL"
    echo "--- extracting bundled interpreter for wheel building ---"
    tar -xzf "$PYTARBALL" -C "$PYWHEEL" --strip-components=1
    "$PYWHEEL/bin/python3" -m pip install -q meson meson-python ninja setuptools wheel
fi
mkdir -p "$WHEELS"
# Wheels are cached across builds; build only what is missing. The cache
# check uses the EXACT pinned filename from pyproject.toml ([tool.appimage]
# packages), not a glob: an old-version wheel in $WHEELS must not make the
# build skip a rebuild and then die later in pip install with a confusing
# version-mismatch error.
pinned_wheel() {
    python3 - "$1" <<'PYEOF'
import re, sys
name = sys.argv[1]
src = open("pyproject.toml").read()
m = re.search(
    r'^\s*"\.\./wheels/(%s-[^"/]+\.whl)"' % re.escape(name), src, re.M)
print(m.group(1) if m else "")
PYEOF
}
for spec in "pycairo pycairo" "dbus-python dbus_python" "PyGObject pygobject"; do
    set -- $spec
    req="$1"; norm="$2"
    pinned="$(cd "$PROJ" && pinned_wheel "$norm")"
    [ -n "$pinned" ] || {
        echo "ERROR: no pinned ../wheels/ entry for '$norm' in pyproject.toml." >&2
        exit 1
    }
    if [ ! -f "$WHEELS/$pinned" ]; then
        echo "--- building wheel: $req (pinned: $pinned) ---"
        "$PYWHEEL/bin/python3" -m pip wheel --no-deps --no-build-isolation \
            -w "$WHEELS" "$req"
    fi
    [ -f "$WHEELS/$pinned" ] || {
        echo "ERROR: pinned wheel missing after build: $WHEELS/$pinned" >&2
        exit 1
    }
done

echo "--- build tool (isolated env) ---"
BPY=""
# Prefer a build-env that actually has the package (a half-aborted
# build leaves an env without it); then system python3; then create.
if [ -x "$STAGE/build-env/bin/python" ] \
    && "$STAGE/build-env/bin/python" -c "import appimage" 2>/dev/null; then
    BPY="$STAGE/build-env/bin/python"
elif python3 -c "import appimage" 2>/dev/null; then
    BPY="python3"
else
    if ! command -v uv >/dev/null 2>&1; then
        echo "appimage package not found. pip install appimage, or install uv: https://docs.astral.sh/uv" >&2
        exit 1
    fi
    uv venv "$STAGE/build-env" >/dev/null
    uv pip install --python "$STAGE/build-env/bin/python" appimage >/dev/null
    BPY="$STAGE/build-env/bin/python"
fi

echo "--- building (downloads toolchain on first run) ---"
(
    cd "$PROJ"
    "$BPY" -m appimage.ctl build --python-archive "$PYTARBALL"
)

# --- smoke guard: prove the bundle actually imports ------------------
# Extract the fresh AppImage and import every module the app needs
# (the split modules, the KDE Wayland D-Bus stack, the UI stack) with
# the BUNDLED interpreter, including linuxtask_main itself plus its
# APP_VERSION (a main module that fails to import or lost its version
# constant must not pass green). A build that cannot pass this is broken.
SMOKE_DIR="$(mktemp -d)"
trap 'rm -rf "$SMOKE_DIR"' EXIT
echo "--- smoke guard: extracting and importing with bundled python ---"
# --appimage-extract always unpacks into the CWD, so extract inside a
# subshell whose cwd is the smoke dir.
(
    cd "$SMOKE_DIR" \
        && "$PROJ/dist/LinuxTask-x86_64.AppImage" --appimage-extract >/dev/null
) 2>"$SMOKE_DIR/extract-err" || {
    echo "ERROR: --appimage-extract failed; see $SMOKE_DIR/extract-err" >&2
    exit 1
}
if ! "$SMOKE_DIR/squashfs-root/python/bin/python3.12" -c "
import recorder, playback, dbus, drivers.factory, evdev, customtkinter
from gi.repository import GLib
import linuxtask_main
print('ok', linuxtask_main.APP_VERSION)
" > "$SMOKE_DIR/smoke.out" 2> "$SMOKE_DIR/smoke.err"; then
    echo "ERROR: bundled-interpreter smoke test failed:" >&2
    cat "$SMOKE_DIR/smoke.err" >&2
    exit 1
fi
echo "smoke guard: $(cat "$SMOKE_DIR/smoke.out")"
echo "--- done: $PROJ/dist/LinuxTask-x86_64.AppImage ---"
