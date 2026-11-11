import json
import unittest
from unittest.mock import patch

from terabox_resolvers import (
    ResolverError,
    ResolvedLinks,
    _js_token,
    _surl,
    _download_link,
    _share_context,
    resolve_terabox_api,
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

    def test_share_context_retries_dragdrop_with_fresh_token(self):
        html = b'var token = "fn%28%22ABCDEF123%22%29";'
        dragdrop = b'{"errno":460030,"errmsg":"dragdrop"}'
        success = b'{"errno":0,"list":[{"server_filename":"video.mp4"}]}'
        with patch("terabox_resolvers._request",
                   side_effect=[html, dragdrop, html, success]) as mocked, \
             patch("terabox_resolvers.time.sleep"):
            base, context = _share_context(
                "https://www.terabox.app/sharing/link?surl=Q8bWTGMxeJteJS__r8YTpA"
            )
        self.assertEqual(base, "https://dm.1024tera.com")
        self.assertEqual(context["data"]["list"][0]["server_filename"], "video.mp4")
        self.assertEqual(mocked.call_count, 4)

    def test_dragdrop_failure_explains_external_api_option(self):
        html = b'var token = "fn%28%22ABCDEF123%22%29";'
        dragdrop = b'{"errno":460030,"errmsg":"dragdrop","request_id":"req-test"}'
        with patch("terabox_resolvers._request",
                   side_effect=[html, dragdrop] * 3), \
             patch("terabox_resolvers.time.sleep"):
            with self.assertRaisesRegex(
                ResolverError, "TERABOX_API_KEY"
            ) as caught:
                _share_context(
                    "https://www.terabox.app/sharing/link?surl=Q8bWTGMxeJteJS__r8YTpA"
                )
        self.assertIn("anonymous share lookup", str(caught.exception))
        self.assertIn("req-test", str(caught.exception))

    def test_download_link_extracts_fresh_dlink(self):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, _limit):
                return b'{"errno":0,"list":[{"dlink":"https://download.example/file"}]}'

        context = {
            "data": {"shareid": 12, "uk": 34, "sign": "sig", "timestamp": 123},
            "headers": {"Referer": "https://dm.1024tera.com/wap/share/filelist?surl=AbCdEf123"},
        }
        with patch("terabox_resolvers.urlopen", return_value=FakeResponse()) as mocked:
            result = _download_link("https://dm.1024tera.com", context, {"fs_id": 56})
        self.assertEqual(result, "https://download.example/file")
        self.assertTrue(mocked.called)
        request = mocked.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")

    def test_download_link_returns_none_when_api_rejects_share(self):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, _limit):
                return b'{"errno":130,"list":[]}'

        context = {
            "data": {"shareid": 12, "uk": 34, "sign": "sig", "timestamp": 123},
            "headers": {},
        }
        with patch("terabox_resolvers.urlopen", return_value=FakeResponse()):
            self.assertIsNone(_download_link(
                "https://dm.1024tera.com", context, {"fs_id": 56}
            ))

    def test_external_api_parses_watch_and_download_links(self):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, _limit):
                return json.dumps({
                    "errno": 0,
                    "list": [{
                        "server_filename": "sample.mp4",
                        "size": 1234,
                        "dlink": "https://cdn.example/download",
                        "stream_url": "https://cdn.example/watch.m3u8",
                    }],
                }).encode()

        with patch("terabox_resolvers.urlopen", return_value=FakeResponse()) as mocked:
            result = resolve_terabox_api(
                "https://terabox.com/s/AbCdEf123", "test-api-key"
            )
        self.assertEqual(result.filename, "sample.mp4")
        self.assertEqual(result.size, 1234)
        self.assertEqual(result.watch_url, "https://cdn.example/watch.m3u8")
        self.assertEqual(result.download_url, "https://cdn.example/download")
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "https://api-v2.teraboxdl.site/api/terabox/extract")
        self.assertEqual(request.get_header("X-api-key"), "test-api-key")
        self.assertEqual(json.loads(request.data)["url"], "https://terabox.com/s/AbCdEf123")

    def test_external_api_rejects_non_https_result_links(self):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, _limit):
                return b'{"errno":0,"list":[{"dlink":"http://unsafe.example/file"}]}'

        with patch("terabox_resolvers.urlopen", return_value=FakeResponse()):
            with self.assertRaisesRegex(ResolverError, "usable HTTPS links"):
                resolve_terabox_api("https://terabox.com/s/AbCdEf123", "test-api-key")

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
