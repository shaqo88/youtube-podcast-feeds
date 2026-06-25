from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yt_dlp

COOKIES_FILE = Path("/tmp/yt_cookies.txt")

PERMANENT_UNAVAILABLE_MARKERS = (
    "video unavailable",
    "private video",
    "video is private",
    "removed by the uploader",
    "terminated",
    "removed for violating",
)


def common_opts() -> dict[str, Any]:
    opts: dict[str, Any] = {
        "extractor_args": {"youtube": {"player_client": ["tv", "web"]}},
    }
    if COOKIES_FILE.exists():
        opts["cookiefile"] = str(COOKIES_FILE)
    if os.environ.get("YTDLP_NO_CHECK_CERTIFICATE") == "1":
        opts["nocheckcertificate"] = True
    return opts


def is_permanently_unavailable(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in PERMANENT_UNAVAILABLE_MARKERS)


def discover_video_ids_by_tab(
    channel_url: str,
    tabs: Iterable[str],
    scan_limit_per_tab: int | None = None,
) -> list[tuple[str, list[str]]]:
    opts = {
        "quiet": True,
        "extract_flat": True,
        "ignoreerrors": True,
        **common_opts(),
    }
    if scan_limit_per_tab:
        opts["playlistend"] = scan_limit_per_tab
    result: list[tuple[str, list[str]]] = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        for tab in tabs:
            info = ydl.extract_info(f"{channel_url.rstrip('/')}/{tab}", download=False)
            if not info:
                continue
            video_ids: list[str] = []
            seen: set[str] = set()
            for entry in info.get("entries") or []:
                video_id = entry.get("id")
                if video_id and video_id not in seen:
                    seen.add(video_id)
                    video_ids.append(video_id)
            result.append((tab, video_ids))
    return result


def discover_video_ids_by_playlist(
    playlist_id: str,
    scan_limit: int | None = None,
) -> list[str]:
    opts = {
        "quiet": True,
        "extract_flat": True,
        "ignoreerrors": True,
        **common_opts(),
    }
    if scan_limit:
        opts["playlistend"] = scan_limit
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/playlist?list={playlist_id}", download=False)
    video_ids: list[str] = []
    seen: set[str] = set()
    for entry in (info or {}).get("entries") or []:
        video_id = entry.get("id")
        if video_id and video_id not in seen:
            seen.add(video_id)
            video_ids.append(video_id)
    return video_ids


def extract_playlist_metadata(playlist_id: str) -> dict[str, Any]:
    opts = {
        "quiet": True,
        "extract_flat": True,
        "playlistend": 1,
        **common_opts(),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/playlist?list={playlist_id}", download=False)
    thumbnails = info.get("thumbnails") or []
    for entry in info.get("entries") or []:
        thumbnails = thumbnails or entry.get("thumbnails") or []
    thumbnail = ""
    if thumbnails:
        thumbnail = max(thumbnails, key=lambda item: item.get("width") or 0).get("url") or ""
    return {
        "id": info.get("id") or playlist_id,
        "title": info.get("title") or "",
        "description": info.get("description") or "",
        "thumbnail": thumbnail,
    }


def extract_channel_metadata(channel_url: str) -> dict[str, Any]:
    opts = {
        "quiet": True,
        "extract_flat": True,
        "playlistend": 1,
        **common_opts(),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(channel_url.rstrip("/"), download=False)
    thumbnails = info.get("thumbnails") or []
    thumbnail = ""
    if thumbnails:
        thumbnail = max(thumbnails, key=lambda item: item.get("width") or 0).get("url") or ""
    return {
        "id": info.get("channel_id") or info.get("id"),
        "title": info.get("channel") or info.get("title") or "",
        "description": info.get("description") or "",
        "thumbnail": thumbnail,
    }


def extract_video_metadata(video_id: str, download: bool = False, output_template: str | None = None) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": not download,
        **common_opts(),
    }
    if download:
        opts.update(
            {
                "format": "bestaudio/best",
                "outtmpl": output_template,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "64",
                    }
                ],
            }
        )
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=download)


def published_yyyymmdd(meta: dict[str, Any]) -> str | None:
    upload_date = meta.get("upload_date")
    if upload_date:
        return upload_date
    timestamp = meta.get("timestamp") or meta.get("release_timestamp")
    if timestamp:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y%m%d")
    return None
