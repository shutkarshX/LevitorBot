"""
TeraBox Link Detection and Resolution Engine for LevitorBot.

Supports ad-free watch and direct download links for TeraBox shares.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Callable
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from database import get_setting

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
    thumbnail_url: Optional[str] = None
    iteraplay_url: str = "https://iteraplay.com"
    success: bool = True
    error_message: Optional[str] = None
    cookie_used: Optional[str] = None


def get_terabox_cookie() -> Optional[str]:
    """Retrieve the TeraBox ndus cookie from database or environment."""
    val = get_setting("terabox_cookie")
    if not val:
        val = os.getenv("TERABOX_COOKIE") or os.getenv("TERABOX_NDUS_COOKIE")
    if not val:
        return None
    val = val.strip().strip('"').strip("'")
    if val.startswith("ndus="):
        val = val[5:].strip()
    return val if val else None



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


def _resolve_via_cookie(share_url: str, cookie: Optional[str] = None) -> Optional[TeraBoxResult]:
    """Attempt extraction using web endpoints and optional ndus session cookie."""
    surl = extract_surl(share_url)
    clean_surl = surl.lstrip("1")

    base_mirrors = [
        "https://dm.1024tera.com",
        "https://www.terabox.app",
        "https://www.terabox.com",
    ]

    for base in base_mirrors:
        headers = {
            "Referer": f"{base}/wap/share/filelist?surl={clean_surl}",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        }
        if cookie:
            headers["Cookie"] = f"ndus={cookie.strip()}"

        try:
            html = _http_request(
                f"{base}/wap/share/filelist?surl={clean_surl}&clearCache=1&t={int(time.time())}",
                headers=headers,
                timeout=5,
            ).decode("utf-8", errors="replace")
        except Exception:
            continue

        token_match = re.search(r'fn%28%22([A-Fa-f0-9]+)%22%29', html)
        token = token_match.group(1) if token_match else None

        params = {
            "app_id": "250528",
            "shorturl": f"1{clean_surl}",
            "root": "1",
            "web": "1",
            "channel": "dubox",
            "clienttype": "0",
            "t": str(int(time.time())),
        }
        if token:
            params["jsToken"] = token

        try:
            endpoint = f"{base}/api/shorturlinfo?{urlencode(params)}"
            data = json.loads(_http_request(endpoint, headers=headers, timeout=6).decode("utf-8"))
        except Exception:
            continue

        if data.get("errno") == 0 and data.get("list"):
            item = data["list"][0]
            filename = str(item.get("server_filename") or "TeraBox Media File")
            size = int(item.get("size") or 0)
            dlink = item.get("dlink")
            thumbs = item.get("thumbs") or {}
            thumb_url = thumbs.get("url3") or thumbs.get("icon")

            stream_url = None
            if cookie and "fs_id" in item and data.get("shareid"):
                stream_params = {
                    "app_id": "250528",
                    "channel": "dubox",
                    "clienttype": "0",
                    "web": "1",
                    "type": "M3U8_AUTO_480",
                    "fid": str(item["fs_id"]),
                    "shareid": str(data.get("shareid")),
                    "uk": str(data.get("uk")),
                    "sign": str(data.get("sign")),
                    "timestamp": str(data.get("timestamp")),
                }
                stream_url = f"{base}/share/streaming?{urlencode(stream_params)}"

            if (not dlink or dlink == "") and "fs_id" in item and cookie:
                try:
                    dl_payload = urlencode({
                        "shareid": data.get("shareid"),
                        "uk": data.get("uk"),
                        "sign": data.get("sign"),
                        "timestamp": data.get("timestamp"),
                        "primaryid": data.get("shareid"),
                        "fid_list": json.dumps([str(item["fs_id"])]),
                    }).encode("utf-8")
                    dl_data = json.loads(_http_request(
                        f"{base}/share/download?app_id=250528&channel=dubox&clienttype=0&web=1",
                        headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
                        data=dl_payload,
                        timeout=10,
                    ).decode("utf-8"))
                    if dl_data.get("errno") == 0 and dl_data.get("dlink"):
                        dlink = dl_data["dlink"]
                except Exception as e:
                    logger.debug("Failed fetching direct dlink from %s: %s", base, e)

            resolved_target = dlink or stream_url

            return TeraBoxResult(
                url=share_url,
                title=filename,
                size=size,
                size_formatted=format_bytes(size),
                watch_url=resolved_target,
                download_url=resolved_target,
                thumbnail_url=thumb_url,
                success=True if resolved_target else False,
                cookie_used=cookie if resolved_target else None,
            )
    return None


def download_terabox_file(
    download_url: str,
    output_path: Path | str,
    cookie: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> bool:
    """Download a TeraBox file stream directly to a local file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Referer": "https://dm.1024tera.com/",
        "Accept": "*/*",
    }
    if cookie:
        clean_cookie = cookie.strip()
        if not clean_cookie.startswith("ndus="):
            clean_cookie = f"ndus={clean_cookie}"
        headers["Cookie"] = clean_cookie

    # Handle HLS streaming playlist
    if "/share/streaming" in download_url or download_url.endswith(".m3u8"):
        req = Request(download_url, headers=headers)
        with urlopen(req, timeout=20) as resp:
            m3u8_text = resp.read().decode("utf-8", errors="replace")

        ts_urls = [line.strip() for line in m3u8_text.splitlines() if line.strip().startswith("http")]
        if not ts_urls:
            raise RuntimeError("No media stream segments found in playlist.")

        total_segments = len(ts_urls)

        def _fetch_segment(item):
            idx, seg_url = item
            seg_req = Request(seg_url, headers={"User-Agent": headers["User-Agent"]})
            with urlopen(seg_req, timeout=25) as seg_resp:
                return idx, seg_resp.read()

        # Download segments in parallel (up to 4 workers)
        with ThreadPoolExecutor(max_workers=min(4, total_segments)) as pool:
            chunks = list(pool.map(_fetch_segment, enumerate(ts_urls)))

        # Reassemble chunks in strict chronological index order
        chunks.sort(key=lambda x: x[0])
        with open(output_path, "wb") as out_f:
            for idx, data in chunks:
                out_f.write(data)
                if progress_callback:
                    progress_callback(idx + 1, total_segments)
        return True

    # Handle direct file download URL
    req = Request(download_url, headers=headers)
    with urlopen(req, timeout=60) as resp, open(output_path, "wb") as f:
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 512 * 1024  # 512 KB
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if progress_callback:
                progress_callback(downloaded, total)
    return True


def resolve_terabox_link(share_url: str) -> TeraBoxResult:
    """
    Main resolution function.
    Tries configured external APIs and cookie methods.
    Always falls back gracefully with iTeraPlay direct link options.
    """
    api_key = os.getenv("TERABOX_API_KEY")
    api_url = os.getenv("TERABOX_API_URL") or "https://api-v2.teraboxdl.site/api/terabox/extract"
    cookie = get_terabox_cookie()

    # 1. Try External Extractor API if configured
    if api_key or os.getenv("TERABOX_API_URL"):
        try:
            res = _resolve_via_external_api(share_url, api_url, api_key)
            if res:
                return res
        except Exception as e:
            logger.warning("External TeraBox API extraction failed: %s", e)

    # 2. Try Cookie-Assisted Method / Web Resolution
    try:
        res = _resolve_via_cookie(share_url, cookie)
        if res:
            return res
    except Exception as e:
        logger.warning("Cookie/Web TeraBox extraction failed: %s", e)

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
