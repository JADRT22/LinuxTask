# -*- coding: utf-8 -*-
"""
LinuxTask - test_updater.py
Description: Headless tests for src/updater.py. No display, no network and
             no hardware: urlopen is patched everywhere it is touched.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import hashlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import updater

_MISSING = object()


def make_payload(tag="v3.5.3", name=updater.ASSET_NAME, url=_MISSING,
                 size=12345, digest=_MISSING,
                 html_url="https://github.com/JADRT22/"
                          "LinuxTask/releases/tag/v3.5.3"):
    """The shape GitHub returns for releases/latest, as measured on v3.5.3.

    `url` and `digest` default to valid values; any explicit value --
    including None -- is put in the payload unchanged.
    """
    if url is _MISSING:
        url = ("https://github.com/JADRT22/LinuxTask/releases/download/"
               "v3.5.3/LinuxTask-x86_64.AppImage")
    if digest is _MISSING:
        digest = "sha256:" + "a" * 64
    return {
        "tag_name": tag,
        "html_url": html_url,
        "assets": [
            {
                "name": "LinuxTask-3.5.3.tar.gz",
                "browser_download_url": "https://example.invalid/src.tar.gz",
                "size": 10,
                "digest": "sha256:" + "b" * 64,
            },
            {
                "name": name,
                "browser_download_url": url,
                "size": size,
                "digest": digest,
            },
        ],
    }


def make_info(payload_bytes, version="9.9.9", asset_url=None):
    """UpdateInfo that matches `payload_bytes`, for download tests."""
    return updater.UpdateInfo(
        version=version,
        asset_url=asset_url or "https://example.invalid/LinuxTask.AppImage",
        asset_size=len(payload_bytes),
        sha256=hashlib.sha256(payload_bytes).hexdigest(),
        html_url="https://example.invalid/release",
    )


class FakeResponse(io.BytesIO):
    """urlopen() stand-in: a context manager over fixed bytes."""

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


class TestVersionComparison(unittest.TestCase):
    def test_plain_triples_parse(self):
        self.assertEqual(updater.version_tuple("3.5.3"), (3, 5, 3))
        self.assertEqual(updater.version_tuple("10.0.1"), (10, 0, 1))

    def test_leading_v_is_stripped(self):
        self.assertEqual(updater.version_tuple("v3.5.3"), (3, 5, 3))
        self.assertEqual(updater.version_tuple("V4.0.0"), (4, 0, 0))

    def test_malformed_versions_are_rejected(self):
        for text in ("", "v", "v3.x", "3..1", "3.5.3-rc1", "3,5,3",
                     "3.5. 3", "٣.٥.٣", None, 3.5, [3, 5]):
            self.assertIsNone(updater.version_tuple(text), repr(text))

    def test_is_newer(self):
        self.assertTrue(updater.is_newer("3.6.0", "3.5.3"))
        self.assertTrue(updater.is_newer("3.5.10", "3.5.9"))
        self.assertFalse(updater.is_newer("3.5.3", "3.5.3"))
        self.assertFalse(updater.is_newer("3.5.2", "3.5.3"))
        self.assertFalse(updater.is_newer("v3.5.3", "3.5.3"))

    def test_garbage_never_produces_a_nag(self):
        self.assertFalse(updater.is_newer("", "3.5.3"))
        self.assertFalse(updater.is_newer("v3.x", "3.5.3"))
        self.assertFalse(updater.is_newer(None, "3.5.3"))
        self.assertFalse(updater.is_newer("3.6.0", "not-a-version"))
        self.assertFalse(updater.is_newer("3.6.0", None))


class TestParseRelease(unittest.TestCase):
    def test_github_shape_is_parsed(self):
        info = updater.parse_release(make_payload())
        self.assertIsNotNone(info)
        self.assertEqual(info.version, "3.5.3")  # no leading v
        self.assertEqual(info.asset_size, 12345)
        self.assertEqual(info.sha256, "a" * 64)
        self.assertTrue(info.asset_url.startswith("https://"))
        self.assertIn("releases/tag", info.html_url)

    def test_missing_asset_yields_none(self):
        self.assertIsNone(updater.parse_release(
            make_payload(name="LinuxTask-aarch64.AppImage")))

    def test_non_https_url_is_rejected(self):
        for url in ("http://github.com/x.AppImage", "ftp://x", "", None, 42):
            self.assertIsNone(
                updater.parse_release(make_payload(url=url)), repr(url))

    def test_path_traversal_in_url_is_not_followed(self):
        # Anything that is not an https URL is refused outright, so a
        # payload cannot point the download at a local file.
        self.assertIsNone(
            updater.parse_release(make_payload(url="file:///etc/passwd")))

    def test_missing_or_malformed_digest_yields_none(self):
        for digest in (None, "", "sha256:", "sha256:" + "A" * 64,
                       "sha256:" + "a" * 63, "md5:" + "a" * 32,
                       "sha256:" + "g" * 64, 42):
            self.assertIsNone(
                updater.parse_release(make_payload(digest=digest)),
                repr(digest))

    def test_missing_digest_key_yields_none(self):
        payload = make_payload()
        payload["assets"][1].pop("digest")
        self.assertIsNone(updater.parse_release(payload))

    def test_invalid_size_yields_none(self):
        for size in (0, -1, None, "12345", 12.5, True):
            self.assertIsNone(
                updater.parse_release(make_payload(size=size)), repr(size))

    def test_non_dict_and_missing_tag_yield_none(self):
        self.assertIsNone(updater.parse_release([]))
        self.assertIsNone(updater.parse_release("payload"))
        payload = make_payload()
        payload.pop("tag_name")
        self.assertIsNone(updater.parse_release(payload))

    def test_assets_not_a_list_yields_none(self):
        payload = make_payload()
        payload["assets"] = {"name": updater.ASSET_NAME}
        self.assertIsNone(updater.parse_release(payload))


class TestFetchLatest(unittest.TestCase):
    def _fetch(self, response):
        with patch("updater.urllib.request.urlopen",
                   return_value=response) as urlopen:
            info = updater.fetch_latest()
        return info, urlopen

    def test_request_shape_and_result(self):
        body = json.dumps(make_payload()).encode("utf-8")
        info, urlopen = self._fetch(FakeResponse(body))
        self.assertEqual(info.version, "3.5.3")

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, updater.RELEASE_API)
        self.assertTrue(
            request.get_header("User-agent").startswith("LinuxTask/"))
        self.assertIn("github.com/JADRT22/LinuxTask",
                      request.get_header("User-agent"))
        self.assertEqual(request.get_header("Accept"),
                         "application/vnd.github+json")
        # Unauthenticated, and no credential is ever sent.
        self.assertIsNone(request.get_header("Authorization"))

    def test_http_error_is_swallowed(self):
        error = urllib.error.HTTPError(
            updater.RELEASE_API, 403, "rate limit exceeded", None, None)
        with patch("updater.urllib.request.urlopen", side_effect=error):
            self.assertIsNone(updater.fetch_latest())

    def test_network_error_is_swallowed(self):
        with patch("updater.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("offline")):
            self.assertIsNone(updater.fetch_latest())

    def test_timeout_is_swallowed(self):
        with patch("updater.urllib.request.urlopen",
                   side_effect=TimeoutError("timed out")):
            self.assertIsNone(updater.fetch_latest())

    def test_bad_json_is_swallowed(self):
        info, _ = self._fetch(FakeResponse(b"<html>not json</html>"))
        self.assertIsNone(info)

    def test_non_dict_payload_is_swallowed(self):
        info, _ = self._fetch(FakeResponse(b'["a list"]'))
        self.assertIsNone(info)

    def test_unusable_release_yields_none(self):
        body = json.dumps(make_payload(digest=None)).encode("utf-8")
        info, _ = self._fetch(FakeResponse(body))
        self.assertIsNone(info)


class TestAppImagePath(unittest.TestCase):
    def test_unset_is_none(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(updater.appimage_path())

    def test_relative_path_is_refused(self):
        with patch.dict(os.environ, {"APPIMAGE": "LinuxTask.AppImage"},
                        clear=True):
            self.assertIsNone(updater.appimage_path())

    def test_missing_file_is_refused(self):
        with patch.dict(os.environ, {"APPIMAGE": "/nonexistent/App.AppImage"},
                        clear=True):
            self.assertIsNone(updater.appimage_path())

    def test_real_file_is_returned(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "LinuxTask-x86_64.AppImage")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("bundle")
            with patch.dict(os.environ, {"APPIMAGE": path}, clear=True):
                self.assertEqual(updater.appimage_path(), path)


class TestDownload(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name

    def _target(self):
        return os.path.join(self.dir, "LinuxTask-x86_64.AppImage")

    def _download(self, info, payload, progress=None):
        with patch("updater.urllib.request.urlopen",
                   return_value=FakeResponse(payload)):
            updater.download(info, self._target(), progress=progress)

    def test_matching_digest_replaces_the_target(self):
        payload = b"new bundle" * 20000          # several chunks
        info = make_info(payload)
        with open(self._target(), "wb") as fh:
            fh.write(b"old bundle")

        seen = []
        self._download(info, payload, progress=lambda done, total:
                       seen.append((done, total)))

        with open(self._target(), "rb") as fh:
            self.assertEqual(fh.read(), payload)
        self.assertEqual(oct(os.stat(self._target()).st_mode & 0o777), "0o755")
        self.assertEqual(os.listdir(self.dir), ["LinuxTask-x86_64.AppImage"])

        self.assertTrue(seen)
        counts = [done for done, _total in seen]
        self.assertEqual(counts, sorted(counts))
        self.assertEqual(seen[-1], (len(payload), len(payload)))

    def test_digest_mismatch_leaves_the_target_untouched(self):
        payload = b"tampered bundle"
        info = make_info(payload)
        info = updater.UpdateInfo(
            version=info.version, asset_url=info.asset_url,
            asset_size=info.asset_size, sha256="f" * 64,
            html_url=info.html_url)
        with open(self._target(), "wb") as fh:
            fh.write(b"old bundle")
        before = os.stat(self._target()).st_mtime_ns

        with self.assertRaises(updater.UpdateError):
            self._download(info, payload)

        with open(self._target(), "rb") as fh:
            self.assertEqual(fh.read(), b"old bundle")
        self.assertEqual(os.stat(self._target()).st_mtime_ns, before)
        self.assertEqual(os.listdir(self.dir), ["LinuxTask-x86_64.AppImage"])

    def test_size_mismatch_is_refused(self):
        payload = b"short"
        info = updater.UpdateInfo(
            version="9.9.9", asset_url="https://example.invalid/a",
            asset_size=len(payload) + 1,
            sha256=hashlib.sha256(payload).hexdigest(), html_url="")

        with self.assertRaises(updater.UpdateError):
            self._download(info, payload)

        self.assertEqual(os.listdir(self.dir), [])

    def test_unwritable_target_is_an_update_error(self):
        payload = b"bundle"
        info = make_info(payload)
        target = os.path.join(self.dir, "missing", "LinuxTask.AppImage")

        with patch("updater.urllib.request.urlopen",
                   return_value=FakeResponse(payload)):
            with self.assertRaises(updater.UpdateError):
                updater.download(info, target)

        self.assertEqual(os.listdir(self.dir), [])

    def test_transport_failure_removes_the_part_file(self):
        payload = b"bundle"
        info = make_info(payload)
        with patch("updater.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("offline")):
            with self.assertRaises(updater.UpdateError):
                updater.download(info, self._target())
        self.assertEqual(os.listdir(self.dir), [])


if __name__ == "__main__":
    unittest.main()
