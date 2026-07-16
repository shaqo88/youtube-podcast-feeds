from __future__ import annotations

import argparse
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import ShowConfig, SourceConfig, is_linked_existing_feed_source, selected_shows
from .drive import download_drive_file, list_drive_files, parse_drive_filename
from .episode_notifications import new_episode_notification
from .episodes import MIN_HOSTED_EPISODE_DURATION_SECONDS, load_episodes, save_episodes
from .existing_feed import (
    download_existing_enclosure,
    enclosure_extension,
    list_existing_feed_items,
    remote_enclosure_info,
)
from .media import convert_to_podcast_mp3, probe_duration_seconds
from .storage import upload_mp3
from .youtube import (
    discover_video_ids_by_playlist,
    discover_video_ids_by_tab,
    extract_video_metadata,
    is_auth_required,
    is_forbidden,
    is_permanently_unavailable,
    is_transient_live_state,
    published_yyyymmdd,
)

LIVE_REFRESH_WINDOW_DAYS = 7
POST_LIVE_DOWNLOAD_DELAY_SECONDS = 60 * 60
ACTIONABLE_POST_LIVE_SKIP_SECONDS = 2 * 60 * 60
HEBREW_TEXT_RE = re.compile(r"[\u0590-\u05ff]")
LATIN_TEXT_RE = re.compile(r"[A-Za-z]")
TRAILING_TIMESTAMP_RE = re.compile(r"\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$")


class SkippedYouTubeEpisode(Exception):
    pass


class SkippedDriveEpisode(Exception):
    pass


def _is_before_start(published: str, source: SourceConfig) -> bool:
    return datetime.strptime(published, "%Y%m%d").date() < source.start_date


def _is_recent_enough_to_refresh(published: str) -> bool:
    if not published:
        return False
    published_date = datetime.strptime(published, "%Y%m%d").date()
    return (datetime.today().date() - published_date).days <= LIVE_REFRESH_WINDOW_DAYS


def _clean_title(title: str | None, video_id: str) -> str:
    if not title:
        return f"Episode {video_id}"
    return TRAILING_TIMESTAMP_RE.sub("", title).rstrip()


def _published_datetime(meta: dict) -> datetime | None:
    timestamp = meta.get("timestamp") or meta.get("release_timestamp")
    if timestamp:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    upload_date = meta.get("upload_date")
    if upload_date:
        return datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)
    return None


def _post_live_age_seconds(meta: dict, now: datetime | None = None) -> int | None:
    published_at = _published_datetime(meta)
    if not published_at:
        return None
    now = now or datetime.now(timezone.utc)
    return int((now - published_at).total_seconds())


def _is_post_live_ready_for_download(meta: dict, now: datetime | None = None) -> bool:
    live_status = str(meta.get("live_status") or "").lower()
    if live_status != "post_live":
        return False
    age_seconds = _post_live_age_seconds(meta, now)
    return age_seconds is not None and age_seconds >= POST_LIVE_DOWNLOAD_DELAY_SECONDS


def _is_active_live_video(meta: dict, now: datetime | None = None) -> bool:
    live_status = str(meta.get("live_status") or "").lower()
    if meta.get("is_live"):
        return True
    if live_status in {"is_live", "is_upcoming"}:
        return True
    return live_status == "post_live" and not _is_post_live_ready_for_download(meta, now)


def _skip_reason_for_youtube_meta(video_id: str, meta: dict, now: datetime | None = None) -> str:
    live_status = str(meta.get("live_status") or "").lower()
    if _is_active_live_video(meta, now):
        if live_status == "post_live":
            age_seconds = _post_live_age_seconds(meta, now)
            if age_seconds is None:
                return f"{video_id}: skipping post-live YouTube stream without publish timestamp"
            return (
                f"{video_id}: skipping post-live YouTube stream "
                f"({age_seconds // 60}m < {POST_LIVE_DOWNLOAD_DELAY_SECONDS // 60}m delay)"
            )
        return f"{video_id}: skipping active YouTube live stream"
    duration = meta.get("duration") or 0
    if duration and duration < MIN_HOSTED_EPISODE_DURATION_SECONDS and live_status != "post_live":
        return (
            f"{video_id}: skipping short YouTube item "
            f"({duration}s < {MIN_HOSTED_EPISODE_DURATION_SECONDS}s)"
        )
    return ""


def _youtube_episode_record(video_id: str, meta: dict, published: str, url: str, size: int) -> dict:
    title = _clean_title(meta.get("title"), video_id)
    return {
        "id": video_id,
        "guid": f"yt:video:{video_id}",
        "source_type": "youtube",
        "title": title,
        "description": meta.get("description") or title,
        "published": published_yyyymmdd(meta) or published,
        "duration": meta.get("duration") or 0,
        "url": url,
        "size": size,
        "source_url": f"https://www.youtube.com/watch?v={video_id}",
    }


def _youtube_video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _skip_report_title(meta: dict | None, video_id: str) -> str:
    title = (meta or {}).get("title")
    if not title:
        return ""
    return _clean_title(title, video_id)


def _youtube_skip_report(
    *,
    show: ShowConfig,
    video_id: str,
    phase: str,
    reason: str,
    meta: dict | None = None,
    retryable: bool = True,
) -> dict:
    return {
        "show_slug": show.slug,
        "video_id": video_id,
        "youtube_url": _youtube_video_url(video_id),
        "title": _skip_report_title(meta, video_id),
        "phase": phase,
        "reason": reason,
        "retryable": retryable,
    }


def _record_youtube_skip(
    skipped_youtube: list[dict] | None,
    *,
    show: ShowConfig,
    video_id: str,
    phase: str,
    reason: str,
    meta: dict | None = None,
    retryable: bool = True,
) -> None:
    if skipped_youtube is None:
        return
    skipped_youtube.append(
        _youtube_skip_report(
            show=show,
            video_id=video_id,
            phase=phase,
            reason=reason,
            meta=meta,
            retryable=retryable,
        )
    )


def _metadata_changed(existing: dict, updated: dict) -> bool:
    keys = ("title", "description", "published", "duration", "source_url")
    return any(existing.get(key) != updated.get(key) for key in keys)


def _preserve_hebrew_localized_fields(existing: dict, updated: dict) -> dict:
    for key in ("title", "description"):
        existing_value = str(existing.get(key) or "")
        updated_value = str(updated.get(key) or "")
        if (
            HEBREW_TEXT_RE.search(existing_value)
            and LATIN_TEXT_RE.search(updated_value)
            and not HEBREW_TEXT_RE.search(updated_value)
        ):
            updated[key] = existing.get(key)
    return updated


def _download_and_store_episode(
    *,
    show: ShowConfig,
    tmp_dir: Path,
    video_id: str,
    meta: dict,
    published: str,
    known: dict[str, dict],
    action: str,
    new_episodes: list[dict] | None = None,
) -> tuple[str, int]:
    is_new = video_id not in known
    print(f"Downloading {meta.get('title') or video_id}")
    output_template = str(tmp_dir / f"{video_id}.%(ext)s")
    meta = extract_video_metadata(video_id, download=True, output_template=output_template)

    mp3_path = tmp_dir / f"{video_id}.mp3"
    if not mp3_path.exists():
        raise FileNotFoundError(f"{video_id}: converted MP3 was not created")

    duration = probe_duration_seconds(mp3_path)
    if duration < MIN_HOSTED_EPISODE_DURATION_SECONDS:
        raise SkippedYouTubeEpisode(
            f"{video_id}: skipping downloaded short YouTube audio "
            f"({duration}s < {MIN_HOSTED_EPISODE_DURATION_SECONDS}s)"
        )

    key = f"{show.r2.prefix}/{video_id}.mp3"
    url = upload_mp3(mp3_path, key)
    size = mp3_path.stat().st_size

    known[video_id] = _youtube_episode_record(video_id, {**meta, "duration": duration}, published, url, size)
    if is_new and new_episodes is not None:
        new_episodes.append(new_episode_notification(show, known[video_id]))
    save_episodes(show.episodes_path, known)
    print(f"{action} {video_id}: {url}")
    return url, size


def _auth_skip(video_id: str) -> str:
    return (
        f"{video_id}: skipping YouTube item because the GitHub runner hit a "
        "YouTube auth/bot-check or access block; will retry on the next sync."
    )


def _forbidden_skip(video_id: str) -> str:
    return (
        f"{video_id}: skipping YouTube item because audio download hit "
        "HTTP Error 403: Forbidden; will retry on the next sync."
    )


def _post_live_unavailable_skip(video_id: str, meta: dict, exc: Exception) -> str:
    age_seconds = _post_live_age_seconds(meta)
    if age_seconds is None:
        age_text = "unknown age"
    else:
        age_text = f"{age_seconds // 60}m after publish"
    return (
        f"{video_id}: skipping post-live YouTube item that is still unavailable "
        f"({age_text}): {exc}"
    )


def _is_actionable_post_live_unavailable(meta: dict, exc: Exception) -> bool:
    if str(meta.get("live_status") or "").lower() != "post_live":
        return False
    age_seconds = _post_live_age_seconds(meta)
    return (
        age_seconds is not None
        and age_seconds >= ACTIONABLE_POST_LIVE_SKIP_SECONDS
        and is_transient_live_state(exc)
    )


def sync_youtube_source(
    show: ShowConfig,
    source: SourceConfig,
    new_episodes: list[dict] | None = None,
    skipped_youtube: list[dict] | None = None,
) -> bool:
    known = load_episodes(show.episodes_path)
    print(f"Loaded {len(known)} known episode records for {show.slug}")
    max_changed = source.max_episodes_per_run
    if max_changed:
        print(f"Will stop after {max_changed} changed YouTube episode(s) for this source")

    if source.type == "youtube_playlist":
        if not source.playlist_id:
            raise ValueError(f"{show.slug}: source.playlist_id is required")
        discovered = [
            (
                "playlist",
                discover_video_ids_by_playlist(
                    source.playlist_id,
                    source.scan_limit_per_tab,
                ),
            )
        ]
    else:
        discovered = discover_video_ids_by_tab(
            source.channel_url,
            source.tabs,
            source.scan_limit_per_tab,
        )
    discovered_count = sum(len(video_ids) for _, video_ids in discovered)
    print(f"Discovered {discovered_count} recent YouTube items for {show.slug}")

    failures: list[str] = []
    new_count = 0
    seen: set[str] = set()

    def reached_batch_limit() -> bool:
        return bool(max_changed and new_count >= max_changed)

    with tempfile.TemporaryDirectory(prefix=f"{show.slug}-") as tmp:
        tmp_dir = Path(tmp)
        for tab, video_ids in discovered:
            print(f"\nScanning {tab}: {len(video_ids)} item(s)")
            for video_id in video_ids:
                if reached_batch_limit():
                    print(f"Reached batch limit of {max_changed} changed YouTube episode(s)")
                    print(f"\n{show.slug}: processed {new_count} changed YouTube episode(s)")
                    return True
                if video_id in seen:
                    continue
                seen.add(video_id)
                if video_id in known:
                    if not _is_recent_enough_to_refresh(known[video_id].get("published", "")):
                        continue

                    try:
                        current_meta = extract_video_metadata(video_id, download=False)
                    except Exception as exc:
                        if is_permanently_unavailable(exc):
                            known[video_id]["unavailable"] = True
                            save_episodes(show.episodes_path, known)
                            print(f"Marked permanently unavailable: {video_id}")
                        elif is_auth_required(exc):
                            reason = _auth_skip(video_id)
                            print(reason)
                            _record_youtube_skip(
                                skipped_youtube,
                                show=show,
                                video_id=video_id,
                                phase="refresh",
                                reason=reason,
                            )
                        elif is_transient_live_state(exc):
                            print(f"{video_id}: skipping transient YouTube live state: {exc}")
                        else:
                            failures.append(f"{video_id}: metadata refresh failed: {exc}")
                        continue

                    current_duration = current_meta.get("duration") or 0
                    stored_duration = known[video_id].get("duration") or 0
                    skip_reason = _skip_reason_for_youtube_meta(video_id, current_meta)
                    if skip_reason:
                        print(skip_reason)
                        continue
                    if current_duration <= stored_duration + 30:
                        existing = known[video_id]
                        updated = {
                            **existing,
                            **_youtube_episode_record(
                                video_id,
                                current_meta,
                                existing.get("published", published_yyyymmdd(current_meta) or ""),
                                existing["url"],
                                existing["size"],
                            ),
                        }
                        if not current_duration and stored_duration:
                            updated["duration"] = stored_duration
                        updated = _preserve_hebrew_localized_fields(existing, updated)
                        if _metadata_changed(existing, updated):
                            known[video_id] = updated
                            save_episodes(show.episodes_path, known)
                            new_count += 1
                            print(f"Updated metadata for {video_id}")
                        continue

                    print(
                        f"Refreshing {video_id}: duration increased from {stored_duration} to {current_duration}"
                    )
                    try:
                        _download_and_store_episode(
                            show=show,
                            tmp_dir=tmp_dir,
                            video_id=video_id,
                            meta=current_meta,
                            published=known[video_id].get("published", published_yyyymmdd(current_meta) or ""),
                            known=known,
                            action="Refreshed",
                            new_episodes=new_episodes,
                        )
                        new_count += 1
                    except SkippedYouTubeEpisode as exc:
                        print(exc)
                    except Exception as exc:
                        if is_auth_required(exc):
                            reason = _auth_skip(video_id)
                            print(reason)
                            _record_youtube_skip(
                                skipped_youtube,
                                show=show,
                                video_id=video_id,
                                phase="refresh",
                                reason=reason,
                                meta=current_meta,
                            )
                            continue
                        if is_forbidden(exc):
                            reason = _forbidden_skip(video_id)
                            print(reason)
                            _record_youtube_skip(
                                skipped_youtube,
                                show=show,
                                video_id=video_id,
                                phase="refresh",
                                reason=reason,
                                meta=current_meta,
                            )
                            continue
                        if _is_actionable_post_live_unavailable(current_meta, exc):
                            reason = _post_live_unavailable_skip(video_id, current_meta, exc)
                            print(reason)
                            _record_youtube_skip(
                                skipped_youtube,
                                show=show,
                                video_id=video_id,
                                phase="refresh",
                                reason=reason,
                                meta=current_meta,
                            )
                            continue
                        if is_transient_live_state(exc):
                            print(f"{video_id}: skipping transient YouTube live state during refresh: {exc}")
                            continue
                        failures.append(f"{video_id}: refresh failed: {exc}")
                    continue

                print(f"\nChecking {video_id}")
                try:
                    meta = extract_video_metadata(video_id, download=False)
                except Exception as exc:
                    if is_permanently_unavailable(exc):
                        known[video_id] = {"id": video_id, "unavailable": True}
                        save_episodes(show.episodes_path, known)
                        print(f"Marked permanently unavailable: {video_id}")
                    elif is_auth_required(exc):
                        reason = _auth_skip(video_id)
                        print(reason)
                        _record_youtube_skip(
                            skipped_youtube,
                            show=show,
                            video_id=video_id,
                            phase="metadata",
                            reason=reason,
                        )
                    elif is_transient_live_state(exc):
                        print(f"{video_id}: skipping transient YouTube live state: {exc}")
                    else:
                        failures.append(f"{video_id}: metadata failed: {exc}")
                    continue

                published = published_yyyymmdd(meta)
                if not published:
                    failures.append(f"{video_id}: missing publish date")
                    continue
                if _is_before_start(published, source):
                    print(f"Stopping {tab}: {video_id} was published {published}, before {source.start_date}")
                    break
                skip_reason = _skip_reason_for_youtube_meta(video_id, meta)
                if skip_reason:
                    print(skip_reason)
                    continue

                try:
                    _download_and_store_episode(
                        show=show,
                        tmp_dir=tmp_dir,
                        video_id=video_id,
                        meta=meta,
                        published=published,
                        known=known,
                        action="Saved",
                        new_episodes=new_episodes,
                    )
                    new_count += 1
                except SkippedYouTubeEpisode as exc:
                    print(exc)
                except Exception as exc:
                    if is_permanently_unavailable(exc):
                        known[video_id] = {
                            "id": video_id,
                            "title": _clean_title(meta.get("title"), video_id),
                            "unavailable": True,
                        }
                        save_episodes(show.episodes_path, known)
                        print(f"Marked permanently unavailable: {video_id}")
                    elif is_auth_required(exc):
                        reason = _auth_skip(video_id)
                        print(reason)
                        _record_youtube_skip(
                            skipped_youtube,
                            show=show,
                            video_id=video_id,
                            phase="download",
                            reason=reason,
                            meta=meta,
                        )
                    elif is_forbidden(exc):
                        reason = _forbidden_skip(video_id)
                        print(reason)
                        _record_youtube_skip(
                            skipped_youtube,
                            show=show,
                            video_id=video_id,
                            phase="download",
                            reason=reason,
                            meta=meta,
                        )
                    elif _is_actionable_post_live_unavailable(meta, exc):
                        reason = _post_live_unavailable_skip(video_id, meta, exc)
                        print(reason)
                        _record_youtube_skip(
                            skipped_youtube,
                            show=show,
                            video_id=video_id,
                            phase="download",
                            reason=reason,
                            meta=meta,
                        )
                    elif is_transient_live_state(exc):
                        print(f"{video_id}: skipping transient YouTube live state during download: {exc}")
                    else:
                        failures.append(f"{video_id}: download failed: {exc}")

    print(f"\n{show.slug}: processed {new_count} changed YouTube episode(s)")
    if failures:
        print(f"{show.slug}: {len(failures)} failure(s)")
        for failure in failures:
            print(f"  - {failure}")
        return False
    return True


def _sync_drive_file(
    show: ShowConfig,
    source: SourceConfig,
    tmp_dir: Path,
    drive_file,
    parsed,
    known: dict[str, dict],
    new_episodes: list[dict] | None = None,
) -> bool:
    existing = known.get(drive_file.id)
    published = parsed.published
    key = f"{show.r2.prefix}/{drive_file.id}.mp3"
    needs_download = (
        existing is None
        or _drive_content_changed(existing, drive_file)
        or not existing.get("url")
        or not existing.get("size")
    )

    if needs_download:
        source_path = tmp_dir / f"{drive_file.id}.{parsed.extension}"
        mp3_path = tmp_dir / f"{drive_file.id}.mp3"
        print(f"Downloading Drive file {drive_file.name}")
        download_drive_file(drive_file.id, source_path)
        convert_to_podcast_mp3(source_path, mp3_path)
        duration = probe_duration_seconds(mp3_path)
        if duration < MIN_HOSTED_EPISODE_DURATION_SECONDS:
            raise SkippedDriveEpisode(
                f"{drive_file.id}: skipping short Drive audio "
                f"({duration}s < {MIN_HOSTED_EPISODE_DURATION_SECONDS}s)"
            )
        url = upload_mp3(mp3_path, key)
        size = mp3_path.stat().st_size
    else:
        url = existing["url"]
        size = existing["size"]
        duration = existing.get("duration") or 0

    record = {
        "id": drive_file.id,
        "guid": f"drive:file:{drive_file.id}",
        "source_type": "drive",
        "source_file_id": drive_file.id,
        "source_folder_id": source.folder_id,
        "source_created_time": drive_file.created_time,
        "source_modified_time": drive_file.modified_time,
        "source_size": drive_file.size,
        "source_md5_checksum": drive_file.md5_checksum,
        "source_name": drive_file.name,
        "published_source": parsed.date_source,
        "title": parsed.title,
        "description": parsed.title,
        "published": published,
        "duration": duration,
        "url": url,
        "size": size,
        "source_url": drive_file.web_view_link or "",
    }
    if existing != record:
        known[drive_file.id] = record
        if existing is None and new_episodes is not None:
            new_episodes.append(new_episode_notification(show, record))
        save_episodes(show.episodes_path, known)
        print(f"{'Saved' if existing is None else 'Updated'} {drive_file.id}: {url}")
        return True
    return False


def _drive_content_changed(existing: dict | None, drive_file) -> bool:
    if existing is None:
        return True
    if not existing.get("url") or not existing.get("size"):
        return True

    existing_checksum = existing.get("source_md5_checksum")
    if drive_file.md5_checksum and existing_checksum:
        return existing_checksum != drive_file.md5_checksum

    existing_source_size = existing.get("source_size")
    if drive_file.size is not None and existing_source_size is not None:
        try:
            return int(existing_source_size) != int(drive_file.size)
        except (TypeError, ValueError):
            return True

    # Metadata-only Drive renames can change modifiedTime. Only fall back to
    # modifiedTime when Drive did not provide stronger content signals.
    if not drive_file.md5_checksum and drive_file.size is None:
        return existing.get("source_modified_time") != drive_file.modified_time
    return False


def _hide_drive_episode(known: dict[str, dict], episode_id: str, reason: str) -> bool:
    episode = known.get(episode_id)
    if not episode or episode.get("source_type") != "drive" or episode.get("unavailable"):
        return False
    episode["unavailable"] = True
    episode["unavailable_reason"] = reason
    return True


def sync_drive_source(show: ShowConfig, source: SourceConfig, new_episodes: list[dict] | None = None) -> bool:
    if not source.folder_id:
        raise ValueError(f"{show.slug}: source.folder_id is required for Drive shows")

    known = load_episodes(show.episodes_path)
    print(f"Loaded {len(known)} known episode records for {show.slug}")
    files = list_drive_files(source.folder_id)
    print(f"Discovered {len(files)} Drive item(s) for {show.slug}")

    failures: list[str] = []
    changed_count = 0
    publishable_ids: set[str] = set()
    current_file_ids = {drive_file.id for drive_file in files}
    with tempfile.TemporaryDirectory(prefix=f"{show.slug}-") as tmp:
        tmp_dir = Path(tmp)
        for drive_file in files:
            parsed = parse_drive_filename(drive_file.name, drive_file.created_time or drive_file.modified_time)
            if not parsed:
                print(f"Skipping draft or unsupported file: {drive_file.name}")
                continue
            if _is_before_start(parsed.published, source):
                print(f"Skipping {drive_file.name}: before {source.start_date}")
                continue
            publishable_ids.add(drive_file.id)
            try:
                if _sync_drive_file(show, source, tmp_dir, drive_file, parsed, known, new_episodes):
                    changed_count += 1
            except SkippedDriveEpisode as exc:
                print(exc)
            except Exception as exc:
                failures.append(f"{drive_file.id}: {drive_file.name}: {exc}")

    for episode_id, episode in list(known.items()):
        if episode.get("source_type") != "drive":
            continue
        if episode.get("source_folder_id") not in (None, source.folder_id):
            continue
        if episode_id in publishable_ids:
            continue
        if episode_id in current_file_ids:
            reason = "Drive file is draft, unsupported, or before the source start date"
        else:
            reason = "Drive file is no longer in the shared folder"
        if _hide_drive_episode(known, episode_id, reason):
            changed_count += 1
            print(f"Removed Drive episode from feed: {episode_id} ({reason})")
            save_episodes(show.episodes_path, known)

    print(f"\n{show.slug}: processed {changed_count} changed Drive episode(s)")
    if failures:
        print(f"{show.slug}: {len(failures)} failure(s)")
        for failure in failures:
            print(f"  - {failure}")
        return False
    return True


def _sync_existing_feed_item(show: ShowConfig, source: SourceConfig, tmp_dir: Path, item, known: dict[str, dict]) -> bool:
    existing = known.get(item.id)
    key = f"{show.r2.prefix}/existing-feed/{item.id}.mp3"
    remote_mode = source.delivery_mode == "remote"
    needs_download = (
        not remote_mode
        and (
            existing is None
            or existing.get("source_enclosure_url") != item.enclosure_url
            or not existing.get("url")
            or not existing.get("size")
        )
    )

    if remote_mode:
        url = item.enclosure_url
        size = item.enclosure_size or (
            existing.get("size") if existing and existing.get("source_enclosure_url") == item.enclosure_url else 0
        )
        mime_type = item.enclosure_type
        if not size or not mime_type:
            remote_size, remote_type = remote_enclosure_info(item.enclosure_url)
            size = size or remote_size
            mime_type = mime_type or remote_type
        if not size:
            raise ValueError(f"{item.title}: could not determine enclosure length")
        duration = item.duration or (existing.get("duration") if existing else 0)
    elif needs_download:
        extension = enclosure_extension(item.enclosure_url, item.enclosure_type)
        source_path = tmp_dir / f"{item.id}.{extension}"
        mp3_path = tmp_dir / f"{item.id}.mp3"
        print(f"Downloading feed enclosure {item.title}")
        download_existing_enclosure(item.enclosure_url, source_path)
        convert_to_podcast_mp3(source_path, mp3_path)
        url = upload_mp3(mp3_path, key)
        size = mp3_path.stat().st_size
        duration = probe_duration_seconds(mp3_path)
        mime_type = "audio/mpeg"
    else:
        url = existing["url"]
        size = existing["size"]
        duration = existing.get("duration") or item.duration
        mime_type = existing.get("mime_type") or "audio/mpeg"

    record = {
        "id": item.id,
        "guid": item.guid,
        "source_type": "existing_feed",
        "delivery_mode": source.delivery_mode,
        "title": item.title,
        "description": item.description,
        "published": item.published,
        "duration": duration,
        "url": url,
        "size": size,
        "mime_type": mime_type or "audio/mpeg",
        "source_url": item.source_url,
        "source_enclosure_url": item.enclosure_url,
        "source_enclosure_type": item.enclosure_type,
    }
    if existing != record:
        known[item.id] = record
        save_episodes(show.episodes_path, known)
        print(f"{'Saved' if existing is None else 'Updated'} existing feed item {item.id}: {url}")
        return True
    return False


def sync_existing_feed_source(
    show: ShowConfig,
    source: SourceConfig,
    new_episodes: list[dict] | None = None,
) -> bool:
    if not source.feed_url:
        raise ValueError(f"{show.slug}: source.feed_url is required for existing_feed shows")
    if is_linked_existing_feed_source(source):
        print(f"{show.slug}: linked existing feed; skipping metadata sync for {source.feed_url}")
        return True

    known = load_episodes(show.episodes_path)
    print(f"Loaded {len(known)} known episode records for {show.slug}")
    items = list_existing_feed_items(source.feed_url, source.scan_limit_per_tab)
    print(f"Discovered {len(items)} existing feed item(s) for {show.slug}")

    failures: list[str] = []
    changed_count = 0
    with tempfile.TemporaryDirectory(prefix=f"{show.slug}-") as tmp:
        tmp_dir = Path(tmp)
        for item in items:
            if _is_before_start(item.published, source):
                print(f"Skipping {item.title}: before {source.start_date}")
                continue
            try:
                if _sync_existing_feed_item(show, source, tmp_dir, item, known):
                    changed_count += 1
            except Exception as exc:
                failures.append(f"{item.id}: {item.title}: {exc}")

    print(f"\n{show.slug}: processed {changed_count} changed existing feed episode(s)")
    if failures:
        print(f"{show.slug}: {len(failures)} failure(s)")
        for failure in failures:
            print(f"  - {failure}")
        return False
    return True


def sync_show(
    show: ShowConfig,
    allowed_source_types: set[str] | None = None,
    new_episodes: list[dict] | None = None,
    skipped_youtube: list[dict] | None = None,
) -> bool:
    handlers: dict[str, Callable[..., bool]] = {
        "youtube": sync_youtube_source,
        "youtube_playlist": sync_youtube_source,
        "drive": sync_drive_source,
        "existing_feed": sync_existing_feed_source,
    }
    ok = True
    for index, source in enumerate(show.sources, start=1):
        if allowed_source_types is not None and source.type not in allowed_source_types:
            print(f"\n{show.slug}: skipping source {index}/{len(show.sources)} ({source.type})")
            continue
        print(f"\n{show.slug}: syncing source {index}/{len(show.sources)} ({source.type})")
        handler = handlers.get(source.type)
        if not handler:
            raise ValueError(f"{show.slug}: unsupported source type {source.type!r}")
        if source.type in {"youtube", "youtube_playlist"}:
            ok = sync_youtube_source(show, source, new_episodes, skipped_youtube) and ok
        else:
            ok = handler(show, source, new_episodes) and ok
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", help="Show slug. Omit to sync all enabled shows.")
    parser.add_argument(
        "--source-type",
        action="append",
        choices=("youtube", "youtube_playlist", "drive", "existing_feed"),
        help="Only sync sources of this type. May be repeated.",
    )
    parser.add_argument(
        "--new-episodes-report",
        type=Path,
        help="Write a JSON report of newly added YouTube/Drive episodes.",
    )
    parser.add_argument(
        "--skip-report",
        type=Path,
        help="Write a JSON report of actionable skipped YouTube episodes.",
    )
    args = parser.parse_args()

    allowed_source_types = set(args.source_type) if args.source_type else None
    ok = True
    new_episodes: list[dict] = []
    skipped_youtube: list[dict] = []
    for show in selected_shows(args.show):
        ok = sync_show(show, allowed_source_types, new_episodes, skipped_youtube) and ok
    if args.new_episodes_report:
        args.new_episodes_report.write_text(
            json.dumps(new_episodes, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.skip_report:
        args.skip_report.write_text(
            json.dumps(skipped_youtube, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
