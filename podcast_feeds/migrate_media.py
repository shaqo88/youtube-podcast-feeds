from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import requests

from .config import selected_shows
from .episodes import load_episodes, save_episodes
from .storage import upload_mp3

HTTP_TIMEOUT = (10, 300)


def _download(url: str, path: Path) -> None:
    with requests.get(url, stream=True, timeout=HTTP_TIMEOUT) as response:
        response.raise_for_status()
        with path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)


def migrate_show(slug: str, dry_run: bool) -> bool:
    show = selected_shows(slug)[0]
    episodes = load_episodes(show.episodes_path)
    changed = 0
    skipped = 0
    public_base = os.environ["R2_PUBLIC_URL"].rstrip("/")

    with tempfile.TemporaryDirectory(prefix=f"{show.slug}-media-") as tmp:
        tmp_dir = Path(tmp)
        for episode_id, episode in episodes.items():
            if episode.get("unavailable"):
                skipped += 1
                continue
            current_url = episode.get("url") or ""
            if not current_url:
                skipped += 1
                continue
            target_key = f"{show.r2.prefix}/{episode_id}.mp3"
            target_url = f"{public_base}/{target_key}"
            if current_url == target_url:
                skipped += 1
                continue

            print(f"{episode_id}: {current_url} -> {target_url}")
            if dry_run:
                changed += 1
                continue

            mp3_path = tmp_dir / f"{episode_id}.mp3"
            _download(current_url, mp3_path)
            uploaded_url = upload_mp3(mp3_path, target_key)
            episode["url"] = uploaded_url
            episode["size"] = mp3_path.stat().st_size
            save_episodes(show.episodes_path, episodes)
            changed += 1

    print(f"{show.slug}: {changed} media record(s) migrated, {skipped} skipped")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", required=True, help="Show slug to migrate.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned copies without uploading.")
    args = parser.parse_args()

    migrate_show(args.show, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
