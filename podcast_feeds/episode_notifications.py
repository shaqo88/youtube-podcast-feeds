from __future__ import annotations

import argparse
import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from .config import ShowConfig, load_show

NOTIFIABLE_SOURCE_TYPES = {"youtube", "youtube_playlist", "drive"}


def new_episode_notification(show: ShowConfig, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "show_slug": show.slug,
        "show_title": show.podcast.title,
        "show_author": show.podcast.author,
        "source_type": record.get("source_type") or "",
        "episode_id": record.get("id") or "",
        "title": record.get("title") or "",
        "published": record.get("published") or "",
        "duration": record.get("duration") or 0,
        "episode_url": record.get("source_url") or "",
        "audio_url": record.get("url") or "",
        "feed_url": show.podcast.feed_url,
        "show_url": show.podcast.website_url,
    }


def load_new_episodes_report(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    episodes = json.loads(path.read_text(encoding="utf-8"))
    return [
        episode
        for episode in episodes
        if episode.get("source_type") in NOTIFIABLE_SOURCE_TYPES
    ]


def load_skipped_youtube_report(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    skips = json.loads(path.read_text(encoding="utf-8"))
    return [skip for skip in skips if skip.get("video_id") and skip.get("youtube_url")]


def detect_new_episodes_from_git(before: str, after: str) -> list[dict[str, Any]]:
    paths = _git_lines(
        "diff",
        "--name-only",
        before,
        after,
        "--",
        "shows/*/episodes.json",
    )
    episodes: list[dict[str, Any]] = []
    for path_text in paths:
        path = Path(path_text)
        if len(path.parts) < 3:
            continue
        show_slug = path.parts[1]
        current = _git_json(after, path_text)
        previous = _git_json(before, path_text)
        try:
            show = load_show(show_slug)
        except Exception as exc:
            print(f"Skipping {show_slug}: could not load show config: {exc}")
            continue
        for episode_id, record in current.items():
            if episode_id in previous:
                continue
            if record.get("source_type") not in NOTIFIABLE_SOURCE_TYPES:
                continue
            episodes.append(new_episode_notification(show, record))
    return episodes


def write_email_outputs(
    *,
    episodes: list[dict[str, Any]],
    repo: str,
    run_url: str,
    output_path: Path,
    summary_path: Path | None = None,
) -> None:
    if not episodes:
        with output_path.open("a", encoding="utf-8") as output:
            output.write("has_new_episodes=false\n")
        return

    subject = _subject(episodes)
    body = _body(episodes, repo, run_url)
    Path("new-episodes-email.txt").write_text(body, encoding="utf-8")

    delimiter = f"NEW_EPISODES_BODY_{uuid.uuid4().hex}"
    with output_path.open("a", encoding="utf-8") as output:
        output.write("has_new_episodes=true\n")
        output.write(f"subject={subject}\n")
        output.write(f"body<<{delimiter}\n")
        output.write(body)
        output.write(f"{delimiter}\n")

    if summary_path:
        with summary_path.open("a", encoding="utf-8") as summary:
            summary.write("## New Torah Pod episodes\n\n")
            summary.write(body)


def write_skipped_youtube_outputs(
    *,
    skips: list[dict[str, Any]],
    repo: str,
    run_url: str,
    output_path: Path,
    summary_path: Path | None = None,
) -> None:
    if not skips:
        with output_path.open("a", encoding="utf-8") as output:
            output.write("has_actionable_skips=false\n")
        return

    subject = _skipped_youtube_subject(skips)
    body = _skipped_youtube_body(skips, repo, run_url)
    Path("skipped-youtube-email.txt").write_text(body, encoding="utf-8")

    delimiter = f"SKIPPED_YOUTUBE_BODY_{uuid.uuid4().hex}"
    with output_path.open("a", encoding="utf-8") as output:
        output.write("has_actionable_skips=true\n")
        output.write(f"subject={subject}\n")
        output.write(f"body<<{delimiter}\n")
        output.write(body)
        output.write(f"{delimiter}\n")

    if summary_path:
        with summary_path.open("a", encoding="utf-8") as summary:
            summary.write("## Skipped YouTube episodes\n\n")
            summary.write(body)


def _subject(episodes: list[dict[str, Any]]) -> str:
    if len(episodes) == 1:
        episode = episodes[0]
        title = _single_line(episode.get("title") or episode.get("show_title") or episode.get("show_slug"))
        return f"New Torah Pod episode: {title}"
    return f"New Torah Pod episodes: {len(episodes)}"


def _skipped_youtube_subject(skips: list[dict[str, Any]]) -> str:
    if len(skips) == 1:
        skip = skips[0]
        label = _single_line(skip.get("title") or skip.get("video_id") or "YouTube episode")
        return f"Torah Pod YouTube episode skipped: {label}"
    return f"Torah Pod YouTube episodes skipped: {len(skips)}"


def _body(episodes: list[dict[str, Any]], repo: str, run_url: str) -> str:
    lines = [
        "New Torah Pod episodes were added and published.",
        "",
        f"Count: {len(episodes)}",
        f"Repository: {repo}",
        f"Run: {run_url}",
        "",
    ]
    for index, episode in enumerate(episodes, start=1):
        source = _source_label(episode.get("source_type"))
        lines.extend(
            [
                f"{index}. {episode.get('show_title') or episode.get('show_slug')}",
                f"Episode: {episode.get('title') or 'untitled'}",
                f"Source: {source}",
                f"Published: {_format_date(episode.get('published'))}",
                f"Duration: {_format_duration(episode.get('duration'))}",
                f"Source URL: {episode.get('episode_url') or 'unknown'}",
                f"Audio URL: {episode.get('audio_url') or 'unknown'}",
                f"Feed URL: {episode.get('feed_url') or 'unknown'}",
                f"Show page: {episode.get('show_url') or 'unknown'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _skipped_youtube_body(skips: list[dict[str, Any]], repo: str, run_url: str) -> str:
    lines = [
        "YouTube episodes were discovered but not added to Torah Pod.",
        "",
        "The sync workflow stayed successful because these look retryable or source-side YouTube blocks.",
        "",
        f"Count: {len(skips)}",
        f"Repository: {repo}",
        f"Run: {run_url}",
        "",
    ]
    for index, skip in enumerate(skips, start=1):
        title = skip.get("title") or "untitled"
        lines.extend(
            [
                f"{index}. {skip.get('show_slug') or 'unknown show'}",
                f"Title: {title}",
                f"Video ID: {skip.get('video_id') or 'unknown'}",
                f"YouTube URL: {skip.get('youtube_url') or 'unknown'}",
                f"Phase: {skip.get('phase') or 'unknown'}",
                f"Retryable: {_format_bool(skip.get('retryable'))}",
                f"Reason: {skip.get('reason') or 'unknown'}",
                "",
            ]
        )
    lines.extend(
        [
            "Action: for YouTube runner/bot-check blocks, rerun Sync Podcast Feeds manually with runner=google-youtube and youtube_auth_mode=none after the Google self-hosted runner is online. Otherwise retry later.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _format_date(value: Any) -> str:
    value = str(value or "")
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value or "unknown"


def _format_duration(value: Any) -> str:
    try:
        seconds = int(value or 0)
    except (TypeError, ValueError):
        seconds = 0
    if seconds <= 0:
        return "unknown"
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _source_label(source_type: Any) -> str:
    if source_type in {"youtube", "youtube_playlist"}:
        return "YouTube"
    if source_type == "drive":
        return "Google Drive"
    return str(source_type or "unknown")


def _format_bool(value: Any) -> str:
    return "yes" if bool(value) else "no"


def _single_line(value: Any) -> str:
    return " ".join(str(value or "").split())


def _git_json(ref: str, path: str) -> dict[str, Any]:
    try:
        content = _git("show", f"{ref}:{path}")
    except subprocess.CalledProcessError:
        return {}
    return json.loads(content) if content.strip() else {}


def _git_lines(*args: str) -> list[str]:
    return [line for line in _git(*args).splitlines() if line.strip()]


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    from_report = subparsers.add_parser("from-report")
    from_report.add_argument("--report", type=Path, required=True)
    from_report.add_argument("--repo", required=True)
    from_report.add_argument("--run-url", required=True)
    from_report.add_argument("--github-output", type=Path)
    from_report.add_argument("--summary", type=Path)

    skipped_youtube = subparsers.add_parser("skipped-youtube-from-report")
    skipped_youtube.add_argument("--report", type=Path, required=True)
    skipped_youtube.add_argument("--repo", required=True)
    skipped_youtube.add_argument("--run-url", required=True)
    skipped_youtube.add_argument("--github-output", type=Path)
    skipped_youtube.add_argument("--summary", type=Path)

    from_git_diff = subparsers.add_parser("from-git-diff")
    from_git_diff.add_argument("--before", required=True)
    from_git_diff.add_argument("--after", required=True)
    from_git_diff.add_argument("--repo", required=True)
    from_git_diff.add_argument("--run-url", required=True)
    from_git_diff.add_argument("--github-output", type=Path)
    from_git_diff.add_argument("--summary", type=Path)

    args = parser.parse_args()
    github_output = args.github_output
    if github_output is None:
        output_env = os.environ.get("GITHUB_OUTPUT")
        if not output_env:
            raise ValueError("--github-output is required when GITHUB_OUTPUT is not set")
        github_output = Path(output_env)

    if args.command == "from-report":
        episodes = load_new_episodes_report(args.report)
    elif args.command == "skipped-youtube-from-report":
        skips = load_skipped_youtube_report(args.report)
        write_skipped_youtube_outputs(
            skips=skips,
            repo=args.repo,
            run_url=args.run_url,
            output_path=github_output,
            summary_path=args.summary,
        )
        return 0
    else:
        episodes = detect_new_episodes_from_git(args.before, args.after)

    write_email_outputs(
        episodes=episodes,
        repo=args.repo,
        run_url=args.run_url,
        output_path=github_output,
        summary_path=args.summary,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
