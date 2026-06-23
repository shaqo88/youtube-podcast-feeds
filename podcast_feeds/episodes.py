from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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


def available_episodes(episodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [episode for episode in episodes.values() if not episode.get("unavailable")]

