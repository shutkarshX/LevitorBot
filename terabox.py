"""
TeraBox Link Detection and Resolution Engine for Snapit (TG-Manager).

Supports ad-free watch and direct download links for TeraBox shares.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

TERABOX_HOST_KEYWORDS = (
    "terabox",
    "1024tera",
    "4funbox",
    "mirrobox",
    "nephobox",
    "momerybox",
    "tibibox",
    "dubox",
    "terashare",
    "terafiles",
    "freeterabox",
)


@dataclass
class TeraBoxResult:
    url: str
    title: str
    size: int
    size_formatted: str
    watch_url: Optional[str] = None
    download_url: Optional[str] = None
    iteraplay_url: str = "https://iteraplay.com"
    success: bool = True
    error_message: Optional[str] = None


def extract_terabox_url(text: str) -> Optional[str]:
    """Find and extract any TeraBox link from message text or caption."""
    if not text:
        return None
    # Match any URL in text
    urls = re.findall(r"https?://[^\s<>\"']+", text)
    for u in urls:
        try:
            parsed = urlparse(u)
            host = (parsed.hostname or "").lower()
            if any(keyword in host for keyword in TERABOX_HOST_KEYWORDS):
                return u.rstrip(".,;!?'\")>]}")
        except Exception:
            continue
    return None


def format_bytes(size: int) -> str:
    """Format bytes into human-readable strings (KB, MB, GB)."""
    if size <= 0:
        return "Unknown size"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_idx = 0
    val = float(size)
    while val >= 1024 and unit_idx < len(units) - 1:
        val /= 1024
        unit_idx += 1
    return f"{val:.1f} {units[unit_idx]}" if unit_idx > 0 else f"{int(val)} B"


def extract_surl(share_url: str) -> str:
    """Extract clean surl shortcode from any TeraBox share URL."""
    try:
        parsed = urlparse(share_url)
        query = parse_qs(parsed.query)
        surl = (query.get("surl") or [None])[0]
        if not surl:
            match = re.search(r"/(?:s|share|wap)/1?([A-Za-z0-9_-]+)", parsed.path)
            if match:
                surl = match.group(1)
        if not surl:
            match = re.search(r"/1([A-Za-z0-9_-]{5,})", parsed.path)
            if match:
                surl = match.group(1)
        if not surl:
            parts = [p.strip() for p in parsed.path.split("/") if p.strip()]
            for part in reversed(parts):
                cleaned = part.lstrip("1")
                if len(cleaned) >= 5 and re.match(r"^[A-Za-z0-9_-]+$", cleaned):
                    surl = cleaned
                    break
        return surl or "file"
    except Exception:
        return "file"


def _http_request(url: str, headers: Optional[dict] = None, data: Optional[bytes] = None, timeout: int = 25) -> bytes:
    req = Request(
        url,
        data=data,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            **(headers or {}),
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _resolve_via_external_api(share_url: str, api_url: str, api_key: Optional[str] = None) -> Optional[TeraBoxResult]:
    """Query an external extraction API."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key:
        headers["X-API-KEY"] = api_key.strip()

    payload = json.dumps({"url": share_url, "page": 1}).encode("utf-8")
    raw = _http_request(api_url, headers=headers, data=payload, timeout=30)
    data = json.loads(raw.decode("utf-8"))

    entries = data.get("list") or (data.get("data", {}).get("list") if isinstance(data.get("data"), dict) else None)
    if not entries and isinstance(data.get("data"), dict):
        entries = [data["data"]]

    if entries and isinstance(entries, list) and len(entries) > 0:
        item = entries[0]
        filename = str(item.get("server_filename") or item.get("filename") or "TeraBox Media File")
        size = int(item.get("size") or item.get("size_bytes") or 0)
        watch = item.get("stream_url") or item.get("watch_url") or item.get("video_url")
        download = item.get("dlink") or item.get("direct_link") or item.get("download_url")

        if watch or download:
            return TeraBoxResult(
                url=share_url,
                title=filename,
                size=size,
                size_formatted=format_bytes(size),
                watch_url=watch,
                download_url=download,
                success=True,
            )
    return None


def _resolve_via_cookie(share_url: str, cookie: str) -> Optional[TeraBoxResult]:
    """Attempt direct extraction using an ndus session cookie."""
    surl = extract_surl(share_url)
    base = "https://dm.1024tera.com"
    headers = {
        "Referer": f"{base}/wap/share/filelist?surl={surl}",
        "Cookie": f"ndus={cookie.strip()}",
    }

    html = _http_request(
        f"{base}/wap/share/filelist?surl={surl}&clearCache=1&t={int(time.time())}",
        headers=headers,
    ).decode("utf-8", errors="replace")

    token_match = re.search(r'fn%28%22([A-Fa-f0-9]+)%22%29', html)
    token = token_match.group(1) if token_match else None

    params = {
        "app_id": "250528",
        "shorturl": f"1{surl}",
        "root": "1",
        "web": "1",
        "channel": "dubox",
        "clienttype": "0",
        "t": str(int(time.time())),
    }
    if token:
        params["jsToken"] = token

    endpoint = f"{base}/api/shorturlinfo?{urlencode(params)}"
    data = json.loads(_http_request(endpoint, headers=headers).decode("utf-8"))

    if data.get("errno") == 0 and data.get("list"):
        item = data["list"][0]
        filename = str(item.get("server_filename") or "TeraBox File")
        size = int(item.get("size") or 0)
        dlink = item.get("dlink")

        if not dlink and "fs_id" in item:
            try:
                dl_payload = urlencode({
                    "shareid": data.get("shareid"),
                    "uk": data.get("uk"),
                    "sign": data.get("sign"),
                    "timestamp": data.get("timestamp"),
                    "primaryid": data.get("shareid"),
                    "fid_list": json.dumps([item["fs_id"]]),
                }).encode("utf-8")
                dl_data = json.loads(_http_request(
                    f"{base}/share/download?app_id=250528&channel=dubox&clienttype=0&web=1",
                    headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
                    data=dl_payload,
                ).decode("utf-8"))
                if dl_data.get("errno") == 0 and dl_data.get("dlink"):
                    dlink = dl_data["dlink"]
            except Exception as e:
                logger.debug("Failed fetching direct dlink: %s", e)

        return TeraBoxResult(
            url=share_url,
            title=filename,
            size=size,
            size_formatted=format_bytes(size),
            watch_url=dlink,
            download_url=dlink,
            success=True,
        )
    return None


def resolve_terabox_link(share_url: str) -> TeraBoxResult:
    """
    Main resolution function.
    Tries configured external APIs and cookie methods.
    Always falls back gracefully with iTeraPlay direct link options.
    """
    api_key = os.getenv("TERABOX_API_KEY")
    api_url = os.getenv("TERABOX_API_URL") or "https://api-v2.teraboxdl.site/api/terabox/extract"
    cookie = os.getenv("TERABOX_COOKIE") or os.getenv("TERABOX_NDUS_COOKIE")

    # 1. Try External Extractor API
    if api_key or os.getenv("TERABOX_API_URL"):
        try:
            res = _resolve_via_external_api(share_url, api_url, api_key)
            if res:
                return res
        except Exception as e:
            logger.warning("External TeraBox API extraction failed: %s", e)

    # 2. Try Cookie-Assisted Method
    if cookie:
        try:
            res = _resolve_via_cookie(share_url, cookie)
            if res:
                return res
        except Exception as e:
            logger.warning("Cookie-assisted TeraBox extraction failed: %s", e)

    # 3. Fallback: Provide ad-free iTeraPlay web player
    surl = extract_surl(share_url)
    display_id = surl if len(surl) <= 16 else f"{surl[:14]}..."

    return TeraBoxResult(
        url=share_url,
        title=f"TeraBox Video/File ({display_id})",
        size=0,
        size_formatted="Stream / Direct Download",
        watch_url=None,
        download_url=None,
        iteraplay_url="https://iteraplay.com",
        success=False,
        error_message=(
            "TeraBox server requires verification. You can watch and download "
            "ad-free directly on iTeraPlay."
        ),
    )
