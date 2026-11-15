# -*- coding: utf-8 -*-
"""
LinuxTask - updater.py
Description: AppImage update check and download. Pure logic: no Tk, no
             threads, no config access. Every function is importable and
             testable without a display and without a network.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import hashlib
import http.client
import importlib
import json
import logging
import os
import re
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger("LinuxTask.updater")

RELEASE_API = "https://api.github.com/repos/JADRT22/LinuxTask/releases/latest"
ASSET_NAME = "LinuxTask-x86_64.AppImage"
CHECK_INTERVAL_SECONDS = 24 * 3600
HTTP_TIMEOUT = 10

_PROJECT_URL = "https://github.com/JADRT22/LinuxTask"
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_CHUNK = 64 * 1024
# A release payload is a few KB; the cap keeps a hostile or broken endpoint
# from making the check read an unbounded body.
_MAX_RELEASE_BYTES = 512 * 1024


class UpdateError(Exception):
    """A download that could not be verified or installed."""


@dataclass(frozen=True)
class UpdateInfo:
    version: str        # "3.5.4", no leading v
    asset_url: str      # https only
    asset_size: int
    sha256: str         # 64 lowercase hex, from the API digest
    html_url: str       # the release page, for the manual fallback


def _app_version():
    """Version of the running app, or None when it cannot be imported.

    main.py imports this module, so the import is deferred: it would be a
    cycle at module level. The AppImage renames main.py to
    linuxtask_main.py, hence the second candidate.
    """
    for module_name in ("main", "linuxtask_main"):
        try:
            module = importlib.import_module(module_name)
        except Exception:  # any import failure means "unknown"
            continue
        version = getattr(module, "APP_VERSION", None)
        if isinstance(version, str) and version:
            return version
    return None


def _user_agent():
    version = _app_version()
    token = "LinuxTask/%s" % version if version else "LinuxTask"
    return "%s (+%s)" % (token, _PROJECT_URL)


def version_tuple(text):
    """'v3.5.4' -> (3, 5, 4); anything unparseable -> None."""
    if not isinstance(text, str):
        return None
    cleaned = text.strip()
    if cleaned[:1] in ("v", "V"):
        cleaned = cleaned[1:]
    if not cleaned:
        return None
    parts = cleaned.split(".")
    if not all(part.isascii() and part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def is_newer(remote, local):
    """True only when both versions parse and remote is greater.

    Garbage never produces a nag: an unreadable version on either side is
    answered with False.
    """
    remote_tuple = version_tuple(remote)
    local_tuple = version_tuple(local)
    if remote_tuple is None or local_tuple is None:
        return False
    return remote_tuple > local_tuple


def parse_release(payload):
    """UpdateInfo from a GitHub `releases/latest` payload, or None.

    Fails closed: a release without an https AppImage asset, a positive
    size and a well-formed sha256 digest yields None, so the app never
    offers to install bytes it cannot verify.
    """
    if not isinstance(payload, dict):
        return None
    version = version_tuple(payload.get("tag_name"))
    if version is None:
        return None
    assets = payload.get("assets")
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if not isinstance(asset, dict) or asset.get("name") != ASSET_NAME:
            continue
        url = asset.get("browser_download_url")
        size = asset.get("size")
        digest = asset.get("digest")
        if not isinstance(url, str) or not url.startswith("https://"):
            return None
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            return None
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            return None
        sha256 = digest[len("sha256:"):]
        if not _DIGEST_RE.match(sha256):
            return None
        html_url = payload.get("html_url")
        if not isinstance(html_url, str):
            html_url = ""
        return UpdateInfo(
            version=".".join(str(part) for part in version),
            asset_url=url,
            asset_size=size,
            sha256=sha256,
            html_url=html_url,
        )
    return None


def fetch_latest(timeout=HTTP_TIMEOUT):
    """One unauthenticated GET for the latest release, or None.

    No exception escapes: offline, rate limits, HTTP errors, malformed
    JSON and unusable payloads all log at debug and return None.
    """
    request = urllib.request.Request(
        RELEASE_API,
        headers={
            "User-Agent": _user_agent(),
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(_MAX_RELEASE_BYTES)
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, http.client.HTTPException) as exc:
        logger.debug("Update check failed: %s", exc)
        return None
    info = parse_release(payload)
    if info is None:
        logger.debug("Latest release has no usable %s asset.", ASSET_NAME)
    return info


def appimage_path():
    """Absolute path of the running AppImage, or None.

    None disables the whole feature: a git checkout or a tools/install.sh
    install has nothing to replace.
    """
    path = os.environ.get("APPIMAGE")
    if not path or not os.path.isabs(path):
        return None
    try:
        if not os.path.isfile(path):
            return None
    except OSError:
        return None
    return path


def _remove_part(part):
    try:
        os.remove(part)
    except OSError:
        pass


def download(info, target_path, progress=None):
    """Stream the asset next to `target_path`, verify it, then replace it.

    The bytes go to `target_path + ".part"` in the same directory, so the
    final `os.replace` is a rename on one filesystem and never opens the
    running file for writing. Any failure removes the .part and raises
    UpdateError; the target is left untouched.

    `progress(done, total)` is called from the caller's thread with a
    monotonically increasing `done`.
    """
    part = target_path + ".part"
    digest = hashlib.sha256()
    done = 0
    request = urllib.request.Request(
        info.asset_url,
        headers={
            "User-Agent": _user_agent(),
            "Accept": "application/octet-stream",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response, \
                open(part, "wb") as handle:
            while True:
                chunk = response.read(_CHUNK)
                if not chunk:
                    break
                handle.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, info.asset_size)
    except (OSError, ValueError, http.client.HTTPException) as exc:
        _remove_part(part)
        raise UpdateError("download failed: %s" % exc) from exc

    if done != info.asset_size:
        _remove_part(part)
        raise UpdateError(
            "size mismatch: got %d bytes, expected %d"
            % (done, info.asset_size))
    actual = digest.hexdigest()
    if actual != info.sha256:
        _remove_part(part)
        raise UpdateError(
            "sha256 mismatch: got %s, expected %s" % (actual, info.sha256))
    try:
        os.chmod(part, 0o755)
        os.replace(part, target_path)
    except OSError as exc:
        _remove_part(part)
        raise UpdateError("could not install the download: %s" % exc) from exc
