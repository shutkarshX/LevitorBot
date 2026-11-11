"""Safe inspection of publicly shared TeraBox pages.

This module deliberately does not log in, solve CAPTCHAs, rotate accounts,
or attempt to bypass share permissions. It only reads metadata exposed by
the public share page.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

ALLOWED_HOSTS = {
    "terabox.com",
    "www.terabox.com",
    "1024terabox.com",
    "www.1024terabox.com",
    "teraboxapp.com",
    "www.teraboxapp.com",
}
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 12


@dataclass(frozen=True)
class PublicShareInfo:
    url: str
    title: str = ""
    description: str = ""


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            value = values.get("content", "").strip()
            if key in {"og:title", "twitter:title"} and value and not self.title:
                self.title = value[:300]
            elif key in {"og:description", "description", "twitter:description"} and value and not self.description:
                self.description = value[:500]

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
            if not self.title:
                self.title = " ".join("".join(self._title_parts).split())[:300]

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
            raise HTTPError(newurl, code, "Redirect to an unapproved host blocked", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def is_terabox_link(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and (parsed.hostname or "").lower() in ALLOWED_HOSTS
        and bool(parsed.path)
    )


def inspect_public_share(value: str) -> PublicShareInfo:
    url = value.strip()
    if not is_terabox_link(url):
        raise ValueError("Only HTTPS links from supported TeraBox domains are accepted.")

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; SnapitPublicShareInspector/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    opener = build_opener(_SafeRedirectHandler())
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or (final.hostname or "").lower() not in ALLOWED_HOSTS:
            raise ValueError("The share page redirected outside supported TeraBox domains.")
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise ValueError("The share URL did not return a public HTML page.")
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError("The public share page exceeded the inspection size limit.")

    parser = _MetadataParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    return PublicShareInfo(
        url=url,
        title=parser.title.strip(),
        description=parser.description.strip(),
    )
