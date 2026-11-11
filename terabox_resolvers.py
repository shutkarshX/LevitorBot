"""Optional TeraBox link resolvers for Snapit.

Native resolution uses public share endpoints only. Cookie-assisted resolution
uses a user-configured ndus cookie. External resolution uses an explicitly
configured JSON resolver endpoint. No CAPTCHA solving, account rotation, or
share-permission bypass is attempted.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ResolvedLinks:
    filename: str
    size: int
    watch_url: str | None
    download_url: str | None
    method: str


class ResolverError(RuntimeError):
    pass


def _request(url: str, *, headers: dict[str, str] | None = None,
             timeout: int = 20) -> bytes:
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        **(headers or {}),
    })
    with urlopen(request, timeout=timeout) as response:
        return response.read(2 * 1024 * 1024 + 1)


def _surl(share_url: str) -> str:
    parsed = urlparse(share_url)
    query = parse_qs(parsed.query)
    value = (query.get("surl") or [None])[0]
    if not value:
        match = re.search(r"/s/1?([A-Za-z0-9_-]+)", parsed.path)
        value = match.group(1) if match else None
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]{6,100}", value):
        raise ResolverError("Could not extract a valid TeraBox share code.")
    return value


def _js_token(html: str) -> str:
    patterns = (
        r'fn%28%22([A-Fa-f0-9]+)%22%29',
        r'eval\(decodeURIComponent\(`([^`]+)`\)\)',
    )
    for pattern in patterns:
        match = re.search(pattern, html)
        if not match:
            continue
        if pattern.startswith("eval"):
            from urllib.parse import unquote
            decoded = unquote(match.group(1))
            token = re.search(r'fn\(["\']([A-Fa-f0-9]+)["\']\)', decoded)
            if token:
                return token.group(1)
        else:
            return match.group(1)
    raise ResolverError("TeraBox did not expose a share-page token.")


def _share_context(share_url: str, cookie: str | None = None) -> tuple[str, dict]:
    surl = _surl(share_url)
    base = "https://dm.1024tera.com"
    headers = {"Referer": f"{base}/wap/share/filelist?surl={surl}"}
    if cookie:
        headers["Cookie"] = f"ndus={cookie}"
    # TeraBox intermittently answers with errno 460030 / "dragdrop".
    # Retry the share-page bootstrap a few times; never attempt CAPTCHA solving.
    last_error = None
    html = ""
    for attempt in range(3):
        try:
            html = _request(
                f"{base}/wap/share/filelist?surl={surl}&clearCache=1&t={int(time.time())}",
                headers=headers,
            ).decode("utf-8", errors="replace")
            token = _js_token(html)
            break
        except Exception as exc:
            last_error = exc
            if attempt == 2:
                raise ResolverError(f"TeraBox share bootstrap failed: {exc}") from exc
            time.sleep(0.5 * (attempt + 1))
    params = {
        "app_id": "250528", "shorturl": f"1{surl}", "root": "1",
        "web": "1", "channel": "dubox", "clienttype": "0",
        "jsToken": token, "t": str(int(time.time())),
    }
    endpoint = f"{base}/api/shorturlinfo?{urlencode(params)}"
    data = json.loads(_request(endpoint, headers=headers).decode("utf-8"))
    if data.get("errno") != 0 or not data.get("list"):
        raise ResolverError(data.get("errmsg") or "TeraBox returned no shared files.")
    return base, {"headers": headers, "data": data, "surl": surl}


def _download_link(base: str, context: dict, item: dict) -> str | None:
    """Ask TeraBox for a fresh share download link using returned share metadata.

    The API may reject public shares or require a logged-in session. In that
    case return None rather than fabricating a direct URL.
    """
    data = context["data"]
    required = ("shareid", "uk", "sign", "timestamp")
    if not all(data.get(key) is not None for key in required) or not item.get("fs_id"):
        return None

    headers = {
        **context["headers"],
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": base,
    }
    params = {
        "app_id": "250528", "channel": "dubox", "clienttype": "0",
        "web": "1", "app": "desktop", "version": "1.0",
    }
    form = {
        "sign": str(data["sign"]),
        "timestamp": str(data["timestamp"]),
        "shareid": str(data["shareid"]),
        "uk": str(data["uk"]),
        "fid_list": json.dumps([int(item["fs_id"])]),
        "primaryid": str(data["shareid"]),
        "type": "dlink",
    }
    endpoint = f"{base}/share/download?{urlencode(params)}"
    request = Request(endpoint, data=urlencode(form).encode("utf-8"), headers=headers)
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read(1024 * 1024 + 1).decode("utf-8"))
        if payload.get("errno") == 0:
            entries = payload.get("list") or []
            if entries and entries[0].get("dlink"):
                return str(entries[0]["dlink"])
    except Exception:
        return None
    return None


def _links_from_context(base: str, context: dict, method: str,
                        cookie_mode: bool = False) -> ResolvedLinks:
    data = context["data"]
    item = data["list"][0]
    filename = str(item.get("server_filename") or "TeraBox file")
    size = int(item.get("size") or 0)
    direct = item.get("dlink") or item.get("direct_link")
    stream = item.get("stream_url")
    if not direct:
        direct = _download_link(base, context, item)

    # The signed HLS URL is constructed only from values returned by TeraBox.
    required = ("shareid", "uk", "sign", "timestamp", "fs_id")
    if not stream and all(data.get(key) is not None for key in required):
        stream_params = {
            "uk": data["uk"], "shareid": data["shareid"],
            "type": "M3U8_AUTO_720", "fid": item["fs_id"],
            "sign": data["sign"], "timestamp": data["timestamp"],
            "jsToken": "", "esl": "1", "isplayer": "1", "ehps": "1",
            "clienttype": "0", "app_id": "250528", "web": "1",
            "channel": "dubox",
        }
        stream = f"{base}/share/streaming?{urlencode(stream_params)}"

    if cookie_mode and not direct:
        params = {
            "app_id": "250528", "jsToken": _js_token(
                _request(
                    f"{base}/wap/share/filelist?surl={context['surl']}",
                    headers=context["headers"],
                ).decode("utf-8", errors="replace")
            ),
            "shorturl": f"1{context['surl']}", "root": "1",
        }
        listing = json.loads(_request(
            f"{base}/share/list?{urlencode(params)}",
            headers=context["headers"],
        ).decode("utf-8"))
        files = listing.get("list") or []
        if files:
            direct = files[0].get("dlink")

    if not stream and not direct:
        raise ResolverError("TeraBox did not return a usable watch or download URL.")
    return ResolvedLinks(filename, size, stream, direct, method)


def resolve_native(share_url: str) -> ResolvedLinks:
    """Resolve public share metadata and any public watch/download links."""
    base, context = _share_context(share_url)
    return _links_from_context(base, context, "native")


def resolve_cookie(share_url: str, ndus_cookie: str) -> ResolvedLinks:
    """Resolve using a user-configured TeraBox ndus cookie."""
    if not ndus_cookie.strip():
        raise ResolverError("TERABOX_NDUS_COOKIE is not configured.")
    base, context = _share_context(share_url, ndus_cookie.strip())
    return _links_from_context(base, context, "cookie", cookie_mode=True)


def resolve_external(share_url: str, endpoint: str) -> ResolvedLinks:
    """Call an explicitly configured JSON resolver endpoint.

    Expected response: {filename, size, watch_url, download_url}.
    The endpoint is opt-in and must be trusted by the administrator.
    """
    if not endpoint.startswith("https://"):
        raise ResolverError("External resolver must use HTTPS.")
    payload = json.dumps({"url": share_url}).encode("utf-8")
    request = Request(endpoint, data=payload, headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Snapit/1.0",
    })
    with urlopen(request, timeout=30) as response:
        result = json.loads(response.read(1024 * 1024 + 1).decode("utf-8"))
    watch = result.get("watch_url") or result.get("stream_url")
    download = result.get("download_url") or result.get("direct_link")
    if not watch and not download:
        raise ResolverError("External resolver returned no usable links.")
    return ResolvedLinks(
        str(result.get("filename") or "TeraBox file"),
        int(result.get("size") or 0), watch, download, "external",
    )


def resolve_with_fallback(share_url: str, *,
                          modes: tuple[str, ...] = ("native",),
                          ndus_cookie: str | None = None,
                          external_endpoint: str | None = None) -> ResolvedLinks:
    """Try enabled resolver modes in order and return the first usable result."""
    errors: list[str] = []
    for mode in modes:
        try:
            if mode == "native":
                return resolve_native(share_url)
            if mode == "cookie":
                return resolve_cookie(share_url, ndus_cookie or "")
            if mode == "external":
                if not external_endpoint:
                    raise ResolverError("External resolver endpoint is not configured.")
                return resolve_external(share_url, external_endpoint)
            raise ResolverError(f"Unknown resolver mode: {mode}")
        except Exception as exc:
            errors.append(f"{mode}: {exc}")
    raise ResolverError("All enabled resolver modes failed. " + " | ".join(errors))


def resolver_settings_from_env() -> tuple[tuple[str, ...], str | None, str | None]:
    """Read resolver order and optional secrets from process environment."""
    raw_modes = os.getenv("TERABOX_RESOLVER_ORDER", "native")
    modes = tuple(
        mode.strip().lower() for mode in raw_modes.split(",")
        if mode.strip()
    )
    allowed = {"native", "external", "cookie"}
    if not modes or any(mode not in allowed for mode in modes):
        raise ResolverError("TERABOX_RESOLVER_ORDER must contain native, external, and/or cookie.")
    return (
        modes,
        os.getenv("TERABOX_NDUS_COOKIE"),
        os.getenv("TERABOX_EXTERNAL_RESOLVER_URL"),
    )
