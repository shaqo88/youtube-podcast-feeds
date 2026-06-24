from __future__ import annotations

import argparse
import tempfile
from datetime import datetime
from pathlib import Path

from .config import ShowConfig, selected_shows
from .episodes import load_episodes, save_episodes
from .storage import upload_mp3
from .youtube import discover_video_ids_by_tab, extract_video_metadata, is_permanently_unavailable, published_yyyymmdd

LIVE_REFRESH_WINDOW_DAYS = 7


def _is_before_start(published: str, show: ShowConfig) -> bool:
    return datetime.strptime(published, "%Y%m%d").date() < show.source.start_date


def _is_recent_enough_to_refresh(published: str) -> bool:
    if not published:
        return False
    published_date = datetime.strptime(published, "%Y%m%d").date()
    return (datetime.today().date() - published_date).days <= LIVE_REFRESH_WINDOW_DAYS


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

    known[video_id] = {
        "id": video_id,
        "title": meta.get("title") or f"Episode {video_id}",
        "description": meta.get("description") or meta.get("title") or video_id,
        "published": published_yyyymmdd(meta) or published,
        "duration": meta.get("duration") or 0,
        "url": url,
        "size": size,
        "source_url": f"https://www.youtube.com/watch?v={video_id}",
    }
    save_episodes(show.episodes_path, known)
    print(f"{action} {video_id}: {url}")
    return url, size


def sync_show(show: ShowConfig) -> bool:
    known = load_episodes(show.episodes_path)
    print(f"Loaded {len(known)} known episode records for {show.slug}")

    discovered = discover_video_ids_by_tab(
        show.source.channel_url,
        show.source.tabs,
        show.source.scan_limit_per_tab,
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
                if _is_before_start(published, show):
                    print(f"Stopping {tab}: {video_id} was published {published}, before {show.source.start_date}")
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
                            "title": meta.get("title") or video_id,
                            "unavailable": True,
                        }
                        save_episodes(show.episodes_path, known)
                        print(f"Marked permanently unavailable: {video_id}")
                    else:
                        failures.append(f"{video_id}: download failed: {exc}")

    print(f"\n{show.slug}: processed {new_count} new episode(s)")
    if failures:
        print(f"{show.slug}: {len(failures)} failure(s)")
        for failure in failures:
            print(f"  - {failure}")
        return False
    return True


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
