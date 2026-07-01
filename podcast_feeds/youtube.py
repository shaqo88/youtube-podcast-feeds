from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yt_dlp

COOKIES_FILE = Path(os.environ.get("YOUTUBE_COOKIES_FILE", "/tmp/yt_cookies.txt"))
DEFAULT_AUTH_MODE = "pot_then_cookie"

PERMANENT_UNAVAILABLE_MARKERS = (
    "video unavailable",
    "private video",
    "video is private",
    "removed by the uploader",
    "terminated",
    "removed for violating",
)

AUTH_REQUIRED_MARKERS = (
    "sign in to confirm you're not a bot",
    "sign in to confirm you\u2019re not a bot",
)


def _cookie_file_available() -> bool:
    return COOKIES_FILE.exists() and COOKIES_FILE.stat().st_size > 0


def _auth_strategies() -> list[str]:
    mode = os.environ.get("YOUTUBE_AUTH_MODE", DEFAULT_AUTH_MODE).strip().lower().replace("-", "_")
    strategies_by_mode = {
        "pot_then_cookie": ["pot", "cookie"],
        "cookie_then_pot": ["cookie", "pot"],
        "pot": ["pot"],
        "cookie": ["cookie"],
        "none": ["plain"],
    }
    strategies = strategies_by_mode.get(mode)
    if not strategies:
        valid = ", ".join(sorted(strategies_by_mode))
        raise ValueError(f"Unsupported YOUTUBE_AUTH_MODE={mode!r}. Expected one of: {valid}")
    if not _cookie_file_available():
        strategies = [strategy for strategy in strategies if strategy != "cookie"]
    return strategies or ["plain"]


def _auth_strategy_description(strategy: str) -> str:
    if strategy == "pot":
        return "bgutil PO-token"
    if strategy == "cookie":
        return "browser cookies"
    return "plain yt-dlp"


def common_opts(strategy: str) -> dict[str, Any]:
    player_client = ["mweb"] if strategy == "pot" else ["tv", "web"]
    opts: dict[str, Any] = {
        "extractor_args": {"youtube": {"player_client": player_client}},
    }
    if strategy == "cookie" and _cookie_file_available():
        opts["cookiefile"] = str(COOKIES_FILE)
    if os.environ.get("YTDLP_NO_CHECK_CERTIFICATE") == "1":
        opts["nocheckcertificate"] = True
    return opts


def extract_info_with_auth(
    url: str,
    *,
    extra_opts: dict[str, Any] | None = None,
    download: bool = False,
) -> dict[str, Any]:
    extra_opts = extra_opts or {}
    strategies = _auth_strategies()
    failures: list[str] = []
    for index, strategy in enumerate(strategies):
        opts = {**common_opts(strategy), **extra_opts}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=download)
        except Exception as exc:
            failures.append(f"{_auth_strategy_description(strategy)}: {exc}")
            if index + 1 < len(strategies):
                next_strategy = _auth_strategy_description(strategies[index + 1])
                print(
                    "YouTube auth strategy "
                    f"{_auth_strategy_description(strategy)} failed; trying {next_strategy}."
                )
                continue
            if len(failures) > 1:
                joined = "\n".join(f"  - {failure}" for failure in failures)
                raise RuntimeError(f"All YouTube auth strategies failed for {url}:\n{joined}") from exc
            raise
    raise RuntimeError(f"No YouTube auth strategies configured for {url}")


def is_permanently_unavailable(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in PERMANENT_UNAVAILABLE_MARKERS)


def is_auth_required(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in AUTH_REQUIRED_MARKERS)


def is_missing_channel_tab(error: Exception) -> bool:
    message = str(error).lower()
    return "does not have a" in message and " tab" in message


def discover_video_ids_by_tab(
    channel_url: str,
    tabs: Iterable[str],
    scan_limit_per_tab: int | None = None,
) -> list[tuple[str, list[str]]]:
    opts: dict[str, Any] = {
        "quiet": True,
        "extract_flat": True,
        "ignoreerrors": True,
    }
    if scan_limit_per_tab:
        opts["playlistend"] = scan_limit_per_tab
    result: list[tuple[str, list[str]]] = []
    for tab in tabs:
        try:
            info = extract_info_with_auth(
                f"{channel_url.rstrip('/')}/{tab}",
                extra_opts=opts,
                download=False,
            )
        except Exception as exc:
            if is_missing_channel_tab(exc):
                print(f"Skipping missing YouTube tab {tab!r}: {exc}")
                continue
            raise
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
    opts: dict[str, Any] = {
        "quiet": True,
        "extract_flat": True,
        "ignoreerrors": True,
    }
    if scan_limit:
        opts["playlistend"] = scan_limit
    info = extract_info_with_auth(
        f"https://www.youtube.com/playlist?list={playlist_id}",
        extra_opts=opts,
        download=False,
    )
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
    }
    info = extract_info_with_auth(
        f"https://www.youtube.com/playlist?list={playlist_id}",
        extra_opts=opts,
        download=False,
    )
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
    }
    info = extract_info_with_auth(
        channel_url.rstrip("/"),
        extra_opts=opts,
        download=False,
    )
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
    return extract_info_with_auth(
        f"https://www.youtube.com/watch?v={video_id}",
        extra_opts=opts,
        download=download,
    )


def published_yyyymmdd(meta: dict[str, Any]) -> str | None:
    upload_date = meta.get("upload_date")
    if upload_date:
        return upload_date
    timestamp = meta.get("timestamp") or meta.get("release_timestamp")
    if timestamp:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y%m%d")
    return None
