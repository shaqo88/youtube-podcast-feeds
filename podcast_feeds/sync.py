from __future__ import annotations

import argparse
import re
import tempfile
from datetime import datetime
from pathlib import Path

from .config import ShowConfig, SourceConfig, selected_shows
from .drive import download_drive_file, list_drive_files, parse_drive_filename
from .episodes import load_episodes, save_episodes
from .media import convert_to_podcast_mp3, probe_duration_seconds
from .storage import upload_mp3
from .youtube import (
    discover_video_ids_by_playlist,
    discover_video_ids_by_tab,
    extract_video_metadata,
    is_permanently_unavailable,
    published_yyyymmdd,
)

LIVE_REFRESH_WINDOW_DAYS = 7
TRAILING_TIMESTAMP_RE = re.compile(r"\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$")


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


def _metadata_changed(existing: dict, updated: dict) -> bool:
    keys = ("title", "description", "published", "duration", "source_url")
    return any(existing.get(key) != updated.get(key) for key in keys)


def _download_and_store_episode(
    *,
    show: ShowConfig,
    tmp_dir: Path,
    video_id: str,
    meta: dict,
    published: str,
    known: dict[str, dict],
    action: str,
) -> tuple[str, int]:
    print(f"Downloading {meta.get('title') or video_id}")
    output_template = str(tmp_dir / f"{video_id}.%(ext)s")
    meta = extract_video_metadata(video_id, download=True, output_template=output_template)

    mp3_path = tmp_dir / f"{video_id}.mp3"
    if not mp3_path.exists():
        raise FileNotFoundError(f"{video_id}: converted MP3 was not created")

    key = f"{show.r2.prefix}/{video_id}.mp3"
    url = upload_mp3(mp3_path, key)
    size = mp3_path.stat().st_size

    known[video_id] = _youtube_episode_record(video_id, meta, published, url, size)
    save_episodes(show.episodes_path, known)
    print(f"{action} {video_id}: {url}")
    return url, size


def sync_youtube_source(show: ShowConfig, source: SourceConfig) -> bool:
    known = load_episodes(show.episodes_path)
    print(f"Loaded {len(known)} known episode records for {show.slug}")

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
    with tempfile.TemporaryDirectory(prefix=f"{show.slug}-") as tmp:
        tmp_dir = Path(tmp)
        for tab, video_ids in discovered:
            print(f"\nScanning {tab}: {len(video_ids)} item(s)")
            for video_id in video_ids:
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
                        else:
                            failures.append(f"{video_id}: metadata refresh failed: {exc}")
                        continue

                    current_duration = current_meta.get("duration") or 0
                    stored_duration = known[video_id].get("duration") or 0
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
                        )
                        new_count += 1
                    except Exception as exc:
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

                try:
                    _download_and_store_episode(
                        show=show,
                        tmp_dir=tmp_dir,
                        video_id=video_id,
                        meta=meta,
                        published=published,
                        known=known,
                        action="Saved",
                    )
                    new_count += 1
                except Exception as exc:
                    if is_permanently_unavailable(exc):
                        known[video_id] = {
                            "id": video_id,
                            "title": _clean_title(meta.get("title"), video_id),
                            "unavailable": True,
                        }
                        save_episodes(show.episodes_path, known)
                        print(f"Marked permanently unavailable: {video_id}")
                    else:
                        failures.append(f"{video_id}: download failed: {exc}")

    print(f"\n{show.slug}: processed {new_count} changed YouTube episode(s)")
    if failures:
        print(f"{show.slug}: {len(failures)} failure(s)")
        for failure in failures:
            print(f"  - {failure}")
        return False
    return True


def _sync_drive_file(show: ShowConfig, tmp_dir: Path, drive_file, parsed, known: dict[str, dict]) -> bool:
    existing = known.get(drive_file.id)
    published = parsed.published
    key = f"{show.r2.prefix}/{drive_file.id}.mp3"
    needs_download = (
        existing is None
        or existing.get("source_modified_time") != drive_file.modified_time
        or not existing.get("url")
        or not existing.get("size")
    )

    if needs_download:
        source_path = tmp_dir / f"{drive_file.id}.{parsed.extension}"
        mp3_path = tmp_dir / f"{drive_file.id}.mp3"
        print(f"Downloading Drive file {drive_file.name}")
        download_drive_file(drive_file.id, source_path)
        convert_to_podcast_mp3(source_path, mp3_path)
        url = upload_mp3(mp3_path, key)
        size = mp3_path.stat().st_size
        duration = probe_duration_seconds(mp3_path)
    else:
        url = existing["url"]
        size = existing["size"]
        duration = existing.get("duration") or 0

    record = {
        "id": drive_file.id,
        "guid": f"drive:file:{drive_file.id}",
        "source_type": "drive",
        "source_file_id": drive_file.id,
        "source_modified_time": drive_file.modified_time,
        "source_name": drive_file.name,
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
        save_episodes(show.episodes_path, known)
        print(f"{'Saved' if existing is None else 'Updated'} {drive_file.id}: {url}")
        return True
    return False


def sync_drive_source(show: ShowConfig, source: SourceConfig) -> bool:
    if not source.folder_id:
        raise ValueError(f"{show.slug}: source.folder_id is required for Drive shows")

    known = load_episodes(show.episodes_path)
    print(f"Loaded {len(known)} known episode records for {show.slug}")
    files = list_drive_files(source.folder_id)
    print(f"Discovered {len(files)} Drive item(s) for {show.slug}")

    failures: list[str] = []
    changed_count = 0
    with tempfile.TemporaryDirectory(prefix=f"{show.slug}-") as tmp:
        tmp_dir = Path(tmp)
        for drive_file in files:
            parsed = parse_drive_filename(drive_file.name)
            if not parsed:
                print(f"Skipping draft or unsupported file: {drive_file.name}")
                continue
            if _is_before_start(parsed.published, source):
                print(f"Skipping {drive_file.name}: before {source.start_date}")
                continue
            try:
                if _sync_drive_file(show, tmp_dir, drive_file, parsed, known):
                    changed_count += 1
            except Exception as exc:
                failures.append(f"{drive_file.id}: {drive_file.name}: {exc}")

    print(f"\n{show.slug}: processed {changed_count} changed Drive episode(s)")
    if failures:
        print(f"{show.slug}: {len(failures)} failure(s)")
        for failure in failures:
            print(f"  - {failure}")
        return False
    return True


def sync_show(show: ShowConfig) -> bool:
    ok = True
    for index, source in enumerate(show.sources, start=1):
        print(f"\n{show.slug}: syncing source {index}/{len(show.sources)} ({source.type})")
        if source.type in {"youtube", "youtube_playlist"}:
            ok = sync_youtube_source(show, source) and ok
        elif source.type == "drive":
            ok = sync_drive_source(show, source) and ok
        else:
            raise ValueError(f"{show.slug}: unsupported source type {source.type!r}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", help="Show slug. Omit to sync all enabled shows.")
    args = parser.parse_args()

    ok = True
    for show in selected_shows(args.show):
        ok = sync_show(show) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
