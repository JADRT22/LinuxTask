# -*- coding: utf-8 -*-
"""
LinuxTask - update_python_lock.py
Description: Regenerates tools/appimage/python-build-standalone.lock, the
             pin that decides which CPython interpreter is baked into the
             AppImage. Run it deliberately (and rebuild) to move the
             bundle to a newer upstream release.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import argparse
import json
import os
import sys
import urllib.request

REPO = "astral-sh/python-build-standalone"
# The interpreter series the AppImage is built for; must keep matching
# [tool.appimage] python in tools/appimage/pyproject.toml and the wheels
# that build.sh source-builds against it.
SERIES = "3.12"
ASSET_NEEDLE = "x86_64-unknown-linux-gnu-install_only_stripped"
LOCK_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'python-build-standalone.lock')
API_URL = "https://api.github.com/repos/%s/releases/latest" % REPO


class NoMatchingAsset(Exception):
    """Upstream published no asset for this series and target."""


def release_url(tag=None):
    """API URL for a release; `tag=None` asks for the latest one."""
    if tag is None:
        return API_URL
    return "https://api.github.com/repos/%s/releases/tags/%s" % (REPO, tag)


def pick_asset(release):
    """Return the asset dict for the pinned series and target.

    `install_only_stripped` is the layout appimage.ctl expects (no
    debug symbols, no build tree), and the free-threaded builds are a
    different ABI, so both the needle and the exclusion are load-bearing.
    """
    candidates = []
    for asset in release.get("assets", []):
        url = asset.get("browser_download_url", "")
        name = asset.get("name", "")
        if not name.startswith("cpython-%s." % SERIES):
            continue
        if ASSET_NEEDLE not in url or "freethreaded" in url:
            continue
        candidates.append(asset)
    if not candidates:
        raise NoMatchingAsset(
            "no cpython-%s %s asset in release %s"
            % (SERIES, ASSET_NEEDLE, release.get("tag_name")))
    return candidates[0]


def digest_of(asset):
    """SHA-256 from the API digest field ("sha256:<hex>") or None."""
    digest = (asset.get("digest") or "").split(":", 1)[-1].strip().lower()
    return digest if len(digest) == 64 else None


def version_of(asset):
    """'cpython-3.12.16+20261026-...' -> '3.12.16'."""
    head = asset["name"].split("+")[0]
    return head.split("-", 1)[1]


def render_lock(release, asset, digest):
    return (
        "# Pinned interpreter for the AppImage build (tools/appimage/build.sh).\n"
        "# Regenerate with: python3 tools/appimage/update_python_lock.py --write\n"
        "# Nothing here floats: the build fails if the download does not hash\n"
        "# to SHA256 below, so two builds of one commit ship one CPython.\n"
        "TAG=%s\n"
        "PYTHON_VERSION=%s\n"
        "URL=%s\n"
        "SHA256=%s\n"
        "SIZE=%s\n"
        % (release["tag_name"], version_of(asset),
           asset["browser_download_url"], digest, asset.get("size", 0))
    )


def fetch(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": "LinuxTask-appimage-lock",
                      "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tag", help="release tag to pin (default: the latest one)")
    parser.add_argument(
        "--write", action="store_true",
        help="overwrite %s instead of printing" % LOCK_PATH)
    args = parser.parse_args(argv)

    try:
        release = fetch(release_url(args.tag))
        asset = pick_asset(release)
        digest = digest_of(asset)
    except (NoMatchingAsset, OSError, ValueError) as exc:
        print("[ERROR] Could not resolve the pin: %s" % exc, file=sys.stderr)
        return 1
    if digest is None:
        print("[ERROR] The API returned no sha256 digest for %s; refusing "
              "to write an unverifiable pin." % asset["name"], file=sys.stderr)
        return 1

    text = render_lock(release, asset, digest)
    if args.write:
        with open(LOCK_PATH, "w", encoding="utf-8") as handle:
            handle.write(text)
        print("Wrote %s\n%s" % (LOCK_PATH, text.rstrip()))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
