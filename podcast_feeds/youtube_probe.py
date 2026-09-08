from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import yt_dlp

from .config import load_enabled_shows
from .episodes import load_episodes
from .youtube import common_opts, recording_is_ready


def choose_probe_video() -> str:
    candidates: list[tuple[str, str]] = []
    for show in load_enabled_shows():
        for episode in load_episodes(show.episodes_path).values():
            if episode.get("source_type") == "youtube" and episode.get("url") and episode.get("published"):
                candidates.append((str(episode["published"]), str(episode["id"])))
    if not candidates:
        raise RuntimeError("No published YouTube episode is available for the fallback probe")
    return max(candidates)[1]


def probe(video_id: str) -> None:
    with tempfile.TemporaryDirectory(prefix="youtube-probe-") as temporary:
        output = str(Path(temporary) / "probe.%(ext)s")
        opts = {
            **common_opts("plain"),
            "format": "bestaudio[protocol!*=m3u8]/bestaudio[protocol!*=m3u8_native]",
            "outtmpl": output,
            "download_ranges": yt_dlp.utils.download_range_func(None, [(0, 5)]),
            "force_keyframes_at_cuts": True,
            "quiet": True,
        }
        with yt_dlp.YoutubeDL(opts) as downloader:
            metadata = downloader.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=True
            )
        if not recording_is_ready(metadata):
            raise RuntimeError("Fallback probe did not resolve a finite completed recording")
        if not any(Path(temporary).iterdir()):
            raise RuntimeError("Fallback probe did not download media")
    print(f"Anonymous fallback probe passed for {video_id}.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id")
    args = parser.parse_args()
    probe(args.video_id or choose_probe_video())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
