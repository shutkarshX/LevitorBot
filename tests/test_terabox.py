"""
Unit tests for TeraBox link parsing, byte formatting, and extraction resolver.
Uses mocked network responses to guarantee fast, deterministic offline execution.
"""
import unittest
from unittest.mock import patch, MagicMock

from terabox import (
    extract_terabox_url,
    extract_surl,
    format_bytes,
    resolve_terabox_link,
    TeraBoxResult,
)


class TestTeraBoxEngine(unittest.TestCase):
    def test_extract_terabox_urls(self):
        urls = [
            ("https://terabox.com/s/1ABCdef123", "https://terabox.com/s/1ABCdef123"),
            ("https://www.teraboxapp.com/sharing/link?surl=ABCdef123", "https://www.teraboxapp.com/sharing/link?surl=ABCdef123"),
            ("https://1024tera.com/s/1XYZ_890", "https://1024tera.com/s/1XYZ_890"),
            ("https://freeterabox.com/s/1foo-bar", "https://freeterabox.com/s/1foo-bar"),
            ("Watch this video: https://4funbox.com/s/1film123 now!", "https://4funbox.com/s/1film123"),
        ]
        for text, expected in urls:
            extracted = extract_terabox_url(text)
            self.assertEqual(extracted, expected)

    def test_extract_non_terabox(self):
        self.assertIsNone(extract_terabox_url("https://google.com/search"))
        self.assertIsNone(extract_terabox_url("hello world"))

    def test_extract_surl(self):
        self.assertEqual(extract_surl("https://terabox.com/s/1ABCdef123"), "ABCdef123")
        self.assertEqual(extract_surl("https://www.teraboxapp.com/sharing/link?surl=XYZ123"), "XYZ123")

    def test_format_bytes(self):
        self.assertEqual(format_bytes(500), "500 B")
        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(format_bytes(1048576 * 50), "50.0 MB")
        self.assertEqual(format_bytes(1073741824 * 2), "2.0 GB")

    @patch("terabox._resolve_via_cookie")
    @patch("terabox._resolve_via_external_api")
    def test_fallback_resolution_mocked(self, mock_ext, mock_cookie):
        """When extractors fail or require verification, return safe iTeraPlay fallback."""
        mock_ext.return_value = None
        mock_cookie.return_value = None

        res = resolve_terabox_link("https://terabox.com/s/1ABCdef123")
        self.assertIsInstance(res, TeraBoxResult)
        self.assertFalse(res.success)
        self.assertEqual(res.iteraplay_url, "https://iteraplay.com")
        self.assertIn("ABCdef123", res.title)

    @patch("terabox._resolve_via_cookie")
    def test_successful_cookie_resolution_mocked(self, mock_cookie):
        """When cookie resolution succeeds, return full streaming result."""
        mock_cookie.return_value = TeraBoxResult(
            url="https://terabox.com/s/1ABCdef123",
            title="Sample_Video.mp4",
            size=10485760,
            size_formatted="10.0 MB",
            watch_url="https://streaming.terabox.com/video.m3u8",
            download_url="https://streaming.terabox.com/video.m3u8",
            thumbnail_url="https://terabox.com/thumb.jpg",
            success=True,
            cookie_used="ndus_sample",
        )

        res = resolve_terabox_link("https://terabox.com/s/1ABCdef123")
        self.assertTrue(res.success)
        self.assertEqual(res.title, "Sample_Video.mp4")
        self.assertEqual(res.size_formatted, "10.0 MB")
        self.assertEqual(res.cookie_used, "ndus_sample")


if __name__ == "__main__":
    unittest.main()
