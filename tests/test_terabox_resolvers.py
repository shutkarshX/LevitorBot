import unittest
from unittest.mock import patch

from terabox_resolvers import (
    ResolverError,
    ResolvedLinks,
    _js_token,
    _surl,
    resolve_with_fallback,
    resolver_settings_from_env,
)


class TeraBoxResolverUnitTests(unittest.TestCase):
    def test_extracts_surl_from_query(self):
        self.assertEqual(_surl("https://www.terabox.app/sharing/link?surl=Q8bWTGMxeJteJS__r8YTpA"),
                         "Q8bWTGMxeJteJS__r8YTpA")

    def test_extracts_surl_from_path(self):
        self.assertEqual(_surl("https://terabox.com/s/1AbCdEf123"), "AbCdEf123")

    def test_rejects_missing_or_invalid_surl(self):
        with self.assertRaises(ResolverError):
            _surl("https://terabox.com/")
        with self.assertRaises(ResolverError):
            _surl("https://terabox.com/s/short")

    def test_extracts_js_token(self):
        self.assertEqual(_js_token('var x = "fn%28%22ABCDEF123%22%29";'), "ABCDEF123")

    def test_fallback_uses_next_enabled_method(self):
        expected = ResolvedLinks("video.mp4", 123, "https://watch.example/v", None, "external")
        with patch("terabox_resolvers.resolve_native", side_effect=ResolverError("native unavailable")), \
             patch("terabox_resolvers.resolve_external", return_value=expected):
            result = resolve_with_fallback(
                "https://terabox.com/s/AbCdEf123",
                modes=("native", "external"),
                external_endpoint="https://resolver.example/api",
            )
        self.assertEqual(result, expected)

    def test_unknown_mode_fails_closed(self):
        with self.assertRaises(ResolverError):
            resolve_with_fallback("https://terabox.com/s/AbCdEf123", modes=("magic",))


if __name__ == "__main__":
    unittest.main()
