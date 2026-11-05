#!/usr/bin/env bash
# Install the host packages tools/appimage/build.sh needs on an Ubuntu
# runner. Both workflows that build the AppImage call this instead of
# carrying their own package list, because a second copy of a list is how
# a missing build dependency stays invisible until someone pushes a tag:
#
#   - v3.5.0: the job built the artifact and attached nothing, because it
#     looked for it at a path build.sh never wrote.
#   - v3.5.1: PyGObject died with "Dependency 'girepository-2.0' is
#     required but not found" -- the list installed the legacy
#     libgirepository1.0-dev, and girepository-2.0.pc ships in
#     libgirepository-2.0-dev. libffi.pc (libffi-dev) was missing from
#     the list too -- PyGObject asks for it one dependency() call after
#     the one that broke, and nothing here proves the runner image had
#     it, which is the reason the list now names every module the build
#     wants rather than the ones that happened to fail.
#
# The modules themselves are listed in build.sh (MODULE_CHECKS), which is
# what the build actually probes. tests/test_appimage_build_deps.py keeps
# the two in step: a module with no package here fails the suite, and so
# does a package that answers no module.
#
# Debian/Ubuntu only: the two callers run on ubuntu runners. Other distros
# install the equivalents named in tools/appimage/build.sh.
#
# Usage: tools/appimage/install-build-deps.sh   (the script prepends sudo
#        itself when the caller is not root)

set -euo pipefail

if ! command -v apt-get >/dev/null 2>&1; then
    echo "ERROR: no apt-get here. This script is for the Ubuntu CI runners;" >&2
    echo "       see the requirements block at the top of tools/appimage/build.sh." >&2
    exit 1
fi

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    SUDO="sudo"
fi

# One package per module build.sh preflights:
#   dbus-1                     -> libdbus-1-dev
#   glib-2.0/gobject-2.0/gio-2.0, girepository-2.0
#                              -> libglib2.0-dev, libgirepository-2.0-dev
#   cairo, cairo-gobject       -> libcairo2-dev
#   libffi                     -> libffi-dev
#   gobject-introspection-1.0  -> gobject-introspection
# The gir1.2-* typelibs are for the interpreter the app runs against during
# the smoke guard, not for compiling.
apt_list=(
    curl pkg-config
    libdbus-1-dev libglib2.0-dev libcairo2-dev libffi-dev
    libgirepository-2.0-dev gobject-introspection
    gir1.2-glib-2.0 gir1.2-girepository-2.0
)

$SUDO apt-get update
# --no-install-recommends on purpose: recommends would pull a desktop's
# worth of extra packages into a job whose only job is compiling four
# wheels.
$SUDO apt-get install -y --no-install-recommends "${apt_list[@]}"

# build.sh needs `uv` (or a python that can already `import appimage`) to
# create its isolated build env. GitHub's runner images set
# PIP_BREAK_SYSTEM_PACKAGES, so this is the one place the install goes to
# the runner's own interpreter; a developer machine that already has uv
# skips it.
if ! command -v uv >/dev/null 2>&1; then
    python3 -m pip install --quiet --upgrade pip uv
fi

echo "--- installed for the AppImage build: ${apt_list[*]} ---"
