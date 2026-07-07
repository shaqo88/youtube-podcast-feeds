from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MIN_HOSTED_EPISODE_DURATION_SECONDS = 2 * 60
HOSTED_SOURCE_TYPES = {"youtube", "drive"}


def load_episodes(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_episodes(path: Path, episodes: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(episodes, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def is_publishable_episode(episode: dict[str, Any]) -> bool:
    if episode.get("unavailable"):
        return False
    if episode.get("source_type") in HOSTED_SOURCE_TYPES:
        try:
            duration = int(episode.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0
        return duration >= MIN_HOSTED_EPISODE_DURATION_SECONDS
    return True


def available_episodes(episodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [episode for episode in episodes.values() if is_publishable_episode(episode)]
