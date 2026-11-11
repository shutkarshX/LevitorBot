import unittest

from terabox import _MetadataParser, is_terabox_link


class TeraBoxUrlValidationTests(unittest.TestCase):
    def test_accepts_supported_https_share_urls(self):
        self.assertTrue(is_terabox_link("https://terabox.com/s/abc123"))
        self.assertTrue(is_terabox_link("https://www.terabox.app/sharing/link?surl=abc123"))
        self.assertTrue(is_terabox_link("https://www.1024terabox.com/sharing/link?surl=abc"))

    def test_rejects_http_and_untrusted_hosts(self):
        self.assertFalse(is_terabox_link("http://terabox.com/s/abc123"))
        self.assertFalse(is_terabox_link("https://example.com/s/abc123"))
        self.assertFalse(is_terabox_link("https://terabox.com.example.org/s/abc123"))

    def test_rejects_embedded_credentials(self):
        self.assertFalse(is_terabox_link("https://user@terabox.com/s/abc123"))
        self.assertFalse(is_terabox_link("https://user:pass@terabox.com/s/abc123"))

    def test_rejects_nonstandard_ports(self):
        self.assertFalse(is_terabox_link("https://terabox.com:8443/s/abc123"))

    def test_rejects_urls_without_a_path(self):
        self.assertFalse(is_terabox_link("https://terabox.com"))

    def test_rejects_malformed_ports(self):
        self.assertFalse(is_terabox_link("https://terabox.com:notaport/s/abc123"))


class TeraBoxMetadataParserTests(unittest.TestCase):
    def test_extracts_open_graph_metadata(self):
        parser = _MetadataParser()
        parser.feed(
            '<html><head>'
            '<meta property="og:title" content="Shared folder">'
            '<meta property="og:description" content="Public files">'
            '</head></html>'
        )
        self.assertEqual(parser.title, "Shared folder")
        self.assertEqual(parser.description, "Public files")

    def test_falls_back_to_html_title(self):
        parser = _MetadataParser()
        parser.feed("<html><head><title>  Example   share </title></head></html>")
        self.assertEqual(parser.title, "Example share")


if __name__ == "__main__":
    unittest.main()
