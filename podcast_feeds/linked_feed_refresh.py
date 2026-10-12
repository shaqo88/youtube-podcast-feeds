"""Capture linked RSS metadata before an offline release render.

This is deliberately separate from site rendering. Each source uses the
existing feed client's request timeout and configured episode scan limit.
Snapshots are replaced atomically so a failed refresh retains the last good
input for a later release build.
"""
from __future__ import annotations

import argparse
import os
import tempfile
from datetime import datetime
from pathlib import Path

from .config import PUBLIC_DIR, ShowConfig, SourceConfig, is_linked_existing_feed_source, selected_shows
from .episode_metadata import read_snapshot, snapshot_path, validated_episodes, write_snapshot
from .existing_feed import list_existing_feed_items
from .site import _linked_feed_episode


def refresh_source(show: ShowConfig, source: SourceConfig, *, public_dir: Path | None = None) -> Path:
    if not is_linked_existing_feed_source(source) or not source.feed_url:
        raise ValueError(f"{show.slug}: source is not a linked feed")
    path = snapshot_path(public_dir or PUBLIC_DIR, show.slug, source.feed_url)
    previous = read_snapshot(path)
    try:
        items = list_existing_feed_items(source.feed_url, source.scan_limit_per_tab)
        refreshed = validated_episodes([
            _linked_feed_episode(item) for item in items
            if not item.published or datetime.strptime(item.published, "%Y%m%d").date() >= source.start_date
        ])
        if not refreshed:
            raise ValueError("linked feed returned no playable episodes")
    except Exception as exc:
        if previous is None:
            raise RuntimeError(f"{show.slug}: no valid initial linked-feed snapshot for {source.feed_url}") from exc
        print(f"{show.slug}: linked refresh failed; retaining previous validated metadata ({type(exc).__name__})")
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".linked-snapshot-", dir=path.parent) as directory:
        temporary = Path(directory) / path.name
        write_snapshot(temporary, refreshed)
        os.replace(temporary, path)
    print(f"{show.slug}: linked snapshot refreshed with {len(refreshed)} episode(s)")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show", help="Refresh one show's linked sources; omit to refresh all enabled shows")
    args = parser.parse_args()
    for show in selected_shows(args.show):
        for source in show.sources:
            if is_linked_existing_feed_source(source):
                refresh_source(show, source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
