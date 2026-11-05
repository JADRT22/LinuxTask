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
# --- interpreter pin ---------------------------------------------------
# Which CPython the bundle ships is decided by
# tools/appimage/python-build-standalone.lock (release tag + sha256), not
# by whatever upstream published last. Resolving `releases/latest` made
# two builds of the same commit produce different bundles, and needed an
# unauthenticated api.github.com call that CI rate-limits. Move the pin
# deliberately: `python3 tools/appimage/update_python_lock.py --write`,
# then rebuild.
# The lock values also name the cache file, so a re-pin can never reuse a
# tarball downloaded for another release.
PYLOCK="$REPO_ROOT/tools/appimage/python-build-standalone.lock"
[ -s "$PYLOCK" ] || {
    echo "ERROR: missing $PYLOCK — the AppImage build has no interpreter pin." >&2
    echo "       Recreate it: python3 tools/appimage/update_python_lock.py --write" >&2
    exit 1
}
PBS_TAG=$(sed -n 's/^TAG=//p' "$PYLOCK")
PBS_PYVER=$(sed -n 's/^PYTHON_VERSION=//p' "$PYLOCK")
PBS_URL=$(sed -n 's/^URL=//p' "$PYLOCK")
PBS_SHA256=$(sed -n 's/^SHA256=//p' "$PYLOCK")
for _pbs_var in PBS_TAG PBS_PYVER PBS_URL PBS_SHA256; do
    [ -n "${!_pbs_var}" ] || {
        echo "ERROR: $_pbs_var is empty in $PYLOCK." >&2
        exit 1
    }
done
# Guard the shape of the pin: the archive must come from the release it
# claims, over https, and never from a redirect target baked into the file.
case "$PBS_URL" in
    "https://github.com/astral-sh/python-build-standalone/releases/download/$PBS_TAG/"*) ;;
    *)
        echo "ERROR: $PYLOCK URL does not match TAG=$PBS_TAG: $PBS_URL" >&2
        exit 1
        ;;
esac

# python-build-standalone tarball, cached OUTSIDE proj/ (staging wipes
# proj/ every run) and handed to appimage.ctl via --python-archive so
# the tool installs the exact same interpreter the wheels target.
PYTARBALL="$STAGE/cpython-${PBS_PYVER}-${PBS_TAG}-x86_64-install_only_stripped.tar.gz"
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
# cli.py backs the headless `play` subcommand (issue #5); main.py
# imports it lazily, so it must ship next to linuxtask_main.py.
cp "$REPO_ROOT/src/cli.py" "$PROJ/cli.py"
cp "$REPO_ROOT/assets/icon.png" "$PROJ/"
cp "$REPO_ROOT/tools/appimage/pyproject.toml" "$PROJ/"
cp "$REPO_ROOT/tools/appimage/LinuxTask.desktop" "$PROJ/"

# Entry point: main.py defines main() directly (used by the
# linuxtask console script via pyproject.toml).
#
# The label/font rewrite lives in tools/appimage/patch_ui.py, not in a
# heredoc: tests/test_appimage_ui_patch.py checks every anchor against the
# real src/main.py, so a UI edit that invalidates a pattern fails in CI
# instead of at the end of a twenty-minute AppImage build.
python3 "$REPO_ROOT/tools/appimage/patch_ui.py" "$PROJ/linuxtask_main.py" || {
    echo "ERROR: staging patch failed; src/main.py no longer matches" \
         "tools/appimage/patch_ui.py." >&2
    exit 1
}

# --- bundled-Python tarball (ABI source for the wheels) ---------------
# Source-built wheels must target the exact ABI of the bundled
# python-build-standalone build ([tool.appimage] python = "3.12"), so the
# pinned archive resolved above feeds both the wheel build and the AppDir
# interpreter.
if [ -f "$PYTARBALL" ] \
        && ! printf '%s  %s\n' "$PBS_SHA256" "$PYTARBALL" \
            | sha256sum --check --status; then
    echo "[WARN] cached tarball does not match the pin; re-downloading" >&2
    rm -f "$PYTARBALL"
fi
if [ ! -f "$PYTARBALL" ]; then
    echo "--- downloading cpython ${PBS_PYVER} (release ${PBS_TAG}) ---"
    curl -fL --retry 3 --continue-at - -o "$PYTARBALL.tmp" "$PBS_URL" || {
        rm -f "$PYTARBALL.tmp"
        echo "ERROR: could not download the pinned interpreter: $PBS_URL" >&2
        exit 1
    }
    # Verification is the whole point of the pin: a truncated, redirected
    # or substituted archive must never reach the bundle.
    if ! printf '%s  %s\n' "$PBS_SHA256" "$PYTARBALL.tmp" \
            | sha256sum --check --status; then
        rm -f "$PYTARBALL.tmp"
        echo "ERROR: sha256 mismatch for the pinned interpreter." >&2
        echo "       expected $PBS_SHA256" >&2
        exit 1
    fi
    # Atomic publish: only a verified download becomes the cache entry, so
    # an interrupted curl can never leave a truncated tarball that the
    # cache-then-skip logic above would trust forever.
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
# (the split modules, all five drivers, the KDE Wayland D-Bus stack,
# the UI stack) with the BUNDLED interpreter, including linuxtask_main
# itself plus its APP_VERSION (a main module that fails to import or
# lost its version constant must not pass green). Every driver is on
# the list: the Sway driver shipped without being imported here at all.
# A build that cannot pass this is broken.
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
import dbus, evdev, customtkinter, Xlib
from gi.repository import GLib
import recorder, playback
import drivers.factory, drivers.sway, drivers.x11, drivers.gnome, drivers.hyprland
import drivers.kde_wayland
import cli
import linuxtask_main
print('ok', linuxtask_main.APP_VERSION)
" > "$SMOKE_DIR/smoke.out" 2> "$SMOKE_DIR/smoke.err"; then
    echo "ERROR: bundled-interpreter smoke test failed:" >&2
    cat "$SMOKE_DIR/smoke.err" >&2
    exit 1
fi
echo "smoke guard: $(cat "$SMOKE_DIR/smoke.out")"
echo "--- done: $PROJ/dist/LinuxTask-x86_64.AppImage ---"
