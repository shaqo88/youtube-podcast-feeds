from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

MIN_HOSTED_EPISODE_DURATION_SECONDS = 2 * 60
HOSTED_SOURCE_TYPES = {"youtube", "drive"}


def load_episodes(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_episodes(path: Path, episodes: dict[str, dict[str, Any]]) -> None:
    save_json_atomic(path, episodes, sort_keys=True)


def save_json_atomic(path: Path, value: Any, *, sort_keys: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=sort_keys) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


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
