from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yt_dlp

COOKIES_FILE = Path(os.environ.get("YOUTUBE_COOKIES_FILE", "/tmp/yt_cookies.txt"))
DEFAULT_AUTH_MODE = "pot_then_cookie"
DEFAULT_ACCEPT_LANGUAGE = "he-IL,he;q=0.9,en-US;q=0.5,en;q=0.3"
METADATA_TIMEOUT_SECONDS = int(os.environ.get("YOUTUBE_METADATA_TIMEOUT_SECONDS", "90"))
DOWNLOAD_TIMEOUT_SECONDS = int(os.environ.get("YOUTUBE_DOWNLOAD_TIMEOUT_SECONDS", "900"))
DOWNLOAD_STALL_SECONDS = int(os.environ.get("YOUTUBE_DOWNLOAD_STALL_SECONDS", "120"))

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
    "gvs po token",
    "po token was not provided",
    "requested format is not available",
)

INVALID_COOKIE_MARKERS = (
    "cookies are no longer valid",
    "cookies have been rotated",
    "account cookies have been rotated",
    "cookie is no longer valid",
)
RECORDING_NOT_READY_MARKER = "youtube recording is not ready"

TRANSIENT_LIVE_MARKERS = (
    "this live event has ended",
    "this live event will begin",
)

FORBIDDEN_MARKERS = (
    "http error 403: forbidden",
)


def _cookie_file_available() -> bool:
    if not COOKIES_FILE.exists() or COOKIES_FILE.stat().st_size <= 0:
        return False
    try:
        return COOKIES_FILE.read_text(encoding="utf-8", errors="replace").startswith(
            "# Netscape HTTP Cookie File"
        )
    except OSError:
        return False


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
    extractor_args: dict[str, dict[str, list[str]]] = {}
    if strategy == "pot":
        extractor_args["youtube"] = {"player_client": ["mweb", "android_vr"]}
    elif strategy == "cookie":
        extractor_args["youtube"] = {"player_client": ["tv", "web"]}
    if strategy == "pot":
        extractor_args["youtube"]["fetch_pot"] = ["always"]
    wpc_browser_path = os.environ.get("YOUTUBE_WPC_BROWSER_PATH")
    if strategy == "pot" and wpc_browser_path:
        extractor_args["youtubepot-wpc"] = {"browser_path": [wpc_browser_path]}
    opts: dict[str, Any] = {
        "http_headers": {
            "Accept-Language": os.environ.get("YOUTUBE_ACCEPT_LANGUAGE", DEFAULT_ACCEPT_LANGUAGE),
        },
        "js_runtimes": {"node": {}},
        "socket_timeout": 30,
        "retries": 1,
        "fragment_retries": 1,
    }
    if extractor_args:
        opts["extractor_args"] = extractor_args
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
    started = time.monotonic()
    deadline_seconds = DOWNLOAD_TIMEOUT_SECONDS if download else METADATA_TIMEOUT_SECONDS
    for index, strategy in enumerate(strategies):
        if time.monotonic() - started >= deadline_seconds:
            raise TimeoutError(f"YouTube {'download' if download else 'metadata'} deadline exceeded")
        opts = {**common_opts(strategy), **extra_opts}
        last_progress = [time.monotonic()]

        def enforce_deadline(status: dict[str, Any]) -> None:
            now = time.monotonic()
            if status.get("status") == "downloading":
                last_progress[0] = now
            if now - started >= deadline_seconds:
                raise TimeoutError(f"YouTube {'download' if download else 'metadata'} deadline exceeded")
            if download and now - last_progress[0] >= DOWNLOAD_STALL_SECONDS:
                raise TimeoutError("YouTube download made no progress before its deadline")

        opts["progress_hooks"] = [enforce_deadline]
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=download)
        except Exception as exc:
            failures.append(f"{_auth_strategy_description(strategy)}: {exc}")
            if index + 1 < len(strategies):
                if strategies[index + 1] == "cookie" and not (
                    is_auth_required(exc) or is_forbidden(exc)
                ):
                    raise
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


def is_invalid_cookie(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in INVALID_COOKIE_MARKERS)


def is_forbidden(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in FORBIDDEN_MARKERS)


def is_transient_live_state(error: Exception) -> bool:
    message = str(error).lower()
    return RECORDING_NOT_READY_MARKER in message or any(
        marker in message for marker in TRANSIENT_LIVE_MARKERS
    )


def recording_is_ready(meta: dict[str, Any]) -> bool:
    """Require a finite duration and a non-transitional live state."""
    live_status = str(meta.get("live_status") or "").lower()
    if meta.get("is_live") or live_status in {"is_live", "is_upcoming", "post_live"}:
        return False
    try:
        return float(meta.get("duration") or 0) > 0
    except (TypeError, ValueError):
        return False


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
    base_url = channel_url.rstrip("/")

    def _extract_video_ids_from_url(url: str) -> list[str]:
        info = extract_info_with_auth(url, extra_opts=opts, download=False)
        if not info:
            return []
        video_ids: list[str] = []
        seen: set[str] = set()
        for entry in info.get("entries") or []:
            video_id = entry.get("id")
            if video_id and video_id not in seen:
                seen.add(video_id)
                video_ids.append(video_id)
        return video_ids

    for tab in tabs:
        tab_url = f"{base_url}/{tab}"
        try:
            video_ids = _extract_video_ids_from_url(tab_url)
        except Exception as exc:
            if is_missing_channel_tab(exc):
                fallback_ids = _extract_video_ids_from_url(base_url)
                if fallback_ids:
                    print(
                        f"Fallback to channel root for {tab!r}: missing YouTube tab; "
                        f"resolved {len(fallback_ids)} video(s)."
                    )
                    result.append((tab, fallback_ids))
                    continue
                print(f"Skipping missing YouTube tab {tab!r}: {exc}")
                continue
            raise
        if not video_ids:
            continue
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
    if not download:
        opts["ignore_no_formats_error"] = True
    if download:
        def reject_unfinished_recording(info: dict[str, Any], *, incomplete: bool) -> str | None:
            if not incomplete and not recording_is_ready(info):
                return RECORDING_NOT_READY_MARKER
            return None

        opts.update(
            {
                "format": "bestaudio[protocol!*=m3u8]/bestaudio[protocol!*=m3u8_native]/bestaudio/best",
                "outtmpl": output_template,
                "match_filter": reject_unfinished_recording,
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
