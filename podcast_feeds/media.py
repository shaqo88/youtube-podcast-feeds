from __future__ import annotations

import subprocess
import os
from pathlib import Path

CONVERSION_TIMEOUT_SECONDS = int(os.environ.get("MEDIA_CONVERSION_TIMEOUT_SECONDS", "300"))


def convert_to_podcast_mp3(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_dest = dest
    if source.resolve() == dest.resolve():
        ffmpeg_dest = dest.with_name(f"{dest.stem}.converted{dest.suffix}")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "44100",
            "-b:a",
            "64k",
            str(ffmpeg_dest),
        ],
        check=True,
        timeout=CONVERSION_TIMEOUT_SECONDS,
    )
    if ffmpeg_dest != dest:
        ffmpeg_dest.replace(dest)


def probe_duration_seconds(path: Path) -> int:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        timeout=60,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    return round(float(value)) if value else 0
