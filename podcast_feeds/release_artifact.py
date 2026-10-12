"""Create and verify immutable releases from checked-in public bytes.

The archive contains only shared public files. Each deployment adds its own
``deployment.json`` after verification, outside the payload digest.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import replace
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Any, Callable

import yaml

from .config import ROOT, load_enabled_shows
from .episode_metadata import read_snapshot, snapshot_path

SCHEMA_VERSION = 1
REPOSITORY = "shaqo88/youtube-podcast-feeds"
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
MAX_PAYLOAD_BYTES = 2_000_000_000


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout.strip()


def tracked_tree(root: Path, revision: str, path: str | None = None) -> dict[str, tuple[str, str]]:
    args = ["ls-tree", "-r", "-z", revision]
    if path:
        args.extend(["--", path])
    result = {}
    for entry in git(root, *args).split(b"\0"):
        if not entry:
            continue
        header, name = entry.split(b"\t", 1)
        mode, kind, oid = header.decode("ascii").split(" ")
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError(f"Unsupported tracked object: {name.decode('utf-8', 'replace')}")
        result[name.decode("utf-8")] = (mode, oid)
    return result


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def safe_path(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and name == path.as_posix() and not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts) and "\\" not in name and ":" not in name


def linked_snapshots(root: Path, public_files: dict[str, dict[str, Any]], public_root: Path | None = None) -> list[dict[str, str]]:
    found = []
    for config_path in sorted((root / "shows").glob("*/config.yml")):
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if config.get("enabled") is False:
            continue
        slug = config.get("slug") or config_path.parent.name
        for source in config.get("sources") or [config.get("source") or {}]:
            if source.get("type") != "existing_feed" or source.get("delivery_mode") != "linked":
                continue
            url = source.get("feed_url")
            if not isinstance(url, str) or not url:
                raise ValueError(f"{slug}: linked source lacks feed URL")
            path = snapshot_path(public_root or root / "public", slug, url)
            relative = path.relative_to(public_root or root / "public").as_posix()
            if relative not in public_files or read_snapshot(path) is None:
                raise ValueError(f"{slug}: missing or invalid linked-feed snapshot: {relative}")
            found.append({"show_slug": slug, "source_url": url, "path": relative, "sha256": public_files[relative]["sha256"]})
    return found


def tool_identity(root: Path, source: dict[str, tuple[str, str]]) -> dict[str, Any]:
    names = [name for name in source if name.startswith("podcast_feeds/") or name in {"requirements.txt", "scripts/check-public-accounts.py"}]
    identity = digest(canonical([[name, source[name][1]] for name in sorted(names)]))
    requirements = root / "requirements.txt"
    versions = {}
    for package in ("feedgen", "Pillow", "PyYAML"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "unavailable"
    return {"renderer_digest": identity, "requirements_sha256": file_digest(requirements) if requirements.exists() else None,
            "python": platform.python_version(), "dependencies": versions}


def previous_feed_blobs(root: Path, revision: str) -> list[dict[str, str]]:
    try:
        parent = git(root, "rev-parse", f"{revision}^1").decode("ascii")
    except subprocess.CalledProcessError:
        return []
    return [{"path": path, "git_blob": oid} for path, (_, oid) in sorted(tracked_tree(root, parent, "public").items())
            if path.endswith("/feed.xml")]


def validate_payload_contracts(root: Path, extracted: Path) -> None:
    """Run the established local feed checks against the unpacked bytes."""
    from .validate import validate_local_show

    for show in load_enabled_shows():
        validate_local_show(replace(show, public_dir=extracted / show.slug))
    if not (extracted / "index.html").is_file() or not (extracted / "search-index.json").is_file():
        raise ValueError("Release payload lacks required public routes")
    try:
        search = json.loads((extracted / "search-index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Release search index is invalid") from exc
    if not isinstance(search, dict) or search.get("schema_version") != 1 or not isinstance(search.get("episodes"), list):
        raise ValueError("Release search index has an unsupported episode contract")
    for episode in search["episodes"]:
        if not isinstance(episode, dict):
            raise ValueError("Release search index contains an invalid episode")
        identity, route, audio_url = (episode.get(key) for key in ("id", "page_url", "audio_url"))
        if not all(isinstance(value, str) and value for value in (identity, route, audio_url)):
            raise ValueError("Release search index contains an incomplete episode")
        page_name = f"{route}index.html"
        if not route.endswith("/") or not safe_path(page_name):
            raise ValueError(f"Release episode route is unsafe: {route}")
        page = extracted.joinpath(*PurePosixPath(page_name).parts)
        if not page.is_file():
            raise ValueError(f"Release episode route is missing: {route}")
        markup = page.read_text(encoding="utf-8")
        if (f'data-episode-id="{html.escape(identity, quote=True)}"' not in markup
                or f'data-episode-src="{html.escape(audio_url, quote=True)}"' not in markup):
            raise ValueError(f"Release episode identity or enclosure differs from its route: {route}")

    try:
        expected_accounts = json.loads((root / "config" / "accounts.production.json").read_text(encoding="utf-8"))
        actual_accounts = json.loads((extracted / "accounts-config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Release account configuration is missing or invalid") from exc
    if actual_accounts != expected_accounts or actual_accounts.get("environment") != "production":
        raise ValueError("Release account configuration differs from production inputs")
    for name in ("storage.js", "accounts-bootstrap.js", "accounts.mjs", "accounts-core.mjs", "firebase-auth.bundle.js"):
        expected = (root / "podcast_feeds" / "web" / name).read_text(encoding="utf-8")
        if name.endswith(".mjs"):
            expected = expected.replace("'./accounts-core.mjs'", "'./accounts-core.js'")
        output_name = name.replace(".mjs", ".js")
        if (extracted / "assets" / output_name).read_text(encoding="utf-8") != expected:
            raise ValueError(f"Release account asset differs from source: {output_name}")


def create_release(root: Path, revision: str, output: Path, *,
                   validate: Callable[[Path, Path], None] = validate_payload_contracts) -> tuple[str, dict[str, Any]]:
    """Package the already-rendered public tree once, with no upstream fetch."""
    if not SHA1.fullmatch(revision) or git(root, "rev-parse", "HEAD").decode("ascii") != revision:
        raise ValueError("Release revision must be the exact checked-out Git commit")
    if git(root, "rev-parse", "--show-object-format") != b"sha1":
        raise ValueError("Only SHA-1 Git object repositories are supported")
    tracked = tracked_tree(root, revision)
    public = {name.removeprefix("public/"): value for name, value in tracked.items() if name.startswith("public/")}
    if not public or "deployment.json" in public:
        raise ValueError("Shared public tree is empty or contains target deployment metadata")
    source = {name: value for name, value in tracked.items() if not name.startswith("public/")}
    for name, (_, oid) in sorted(source.items()):
        path = root / name
        if not path.is_file() or git_blob(path.read_bytes()) != oid:
            raise ValueError(f"Source input differs from committed revision: {name}")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "payload.zip"
    files: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zip_file:
        for name, (mode, oid) in sorted(public.items()):
            if not safe_path(name):
                raise ValueError(f"Unsafe public path: {name}")
            path = root / "public" / name
            data = path.read_bytes()
            if git_blob(data) != oid:
                raise ValueError(f"Public file differs from committed revision: {name}")
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100644 << 16)
            zip_file.writestr(info, data)
            files[name] = {"sha256": digest(data), "size": len(data), "git_blob": oid}
    snapshots = linked_snapshots(root, files)
    feed_dates = {}
    for name in sorted(files):
        if name.endswith("/feed.xml"):
            channel = ET.fromstring((root / "public" / name).read_bytes()).find("channel")
            feed_dates[name] = channel.findtext("lastBuildDate") if channel is not None else None
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "repository": REPOSITORY,
        "source_revision": revision,
        "source_tree": git(root, "rev-parse", f"{revision}^{{tree}}").decode("ascii"),
        "public_tree": git(root, "rev-parse", f"{revision}:public").decode("ascii"),
        "source_inputs_digest": digest(canonical([[name, *source[name]] for name in sorted(source)])),
        "linked_feed_snapshots": snapshots,
        "previous_feed_blobs": previous_feed_blobs(root, revision),
        "build_instant": os.environ.get("TORAH_POD_BUILD_INSTANT"),
        "rendered_feed_dates": feed_dates,
        "accounts_environment": os.environ.get("ACCOUNTS_ENVIRONMENT", "production"),
        "tool_identity": tool_identity(root, source),
        "files": files,
        "content_digest": digest(canonical(files)),
        "payload_digest": file_digest(archive),
        "payload_size": archive.stat().st_size,
    }
    manifest_bytes = canonical(manifest)
    release_id = digest(manifest_bytes)
    (output / "manifest.json").write_bytes(manifest_bytes)
    with tempfile.TemporaryDirectory(prefix="release-validate-") as directory:
        extracted = Path(directory)
        verify_release(root, revision, manifest_bytes, archive, extracted, require_main=False)
        validate(root, extracted)
    return release_id, manifest


def verify_release(root: Path, revision: str, manifest_bytes: bytes, archive: Path, destination: Path,
                   *, require_main: bool = True) -> str:
    """Reject altered, incomplete, foreign, or non-Git payloads before use."""
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid release manifest") from exc
    if not isinstance(manifest, dict) or canonical(manifest) != manifest_bytes or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported or noncanonical release manifest")
    if manifest.get("repository") != REPOSITORY or manifest.get("source_revision") != revision or not SHA1.fullmatch(revision):
        raise ValueError("Release provenance does not match requested repository/revision")
    if git(root, "rev-parse", "HEAD").decode("ascii") != revision:
        raise ValueError("Checkout differs from release source revision")
    if require_main and subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", revision, "origin/main"]).returncode:
        raise ValueError("Release source revision is not on main")
    if manifest.get("source_tree") != git(root, "rev-parse", f"{revision}^{{tree}}").decode("ascii") or manifest.get("public_tree") != git(root, "rev-parse", f"{revision}:public").decode("ascii"):
        raise ValueError("Release source/public tree is not trusted Git content")
    tracked = tracked_tree(root, revision)
    source = {name: value for name, value in tracked.items() if not name.startswith("public/")}
    if manifest.get("source_inputs_digest") != digest(canonical([[name, *source[name]] for name in sorted(source)])):
        raise ValueError("Release source input identity mismatch")
    expected_tool = tool_identity(root, source)
    claimed_tool = manifest.get("tool_identity")
    if not isinstance(claimed_tool, dict) or any(claimed_tool.get(key) != expected_tool[key] for key in ("renderer_digest", "requirements_sha256")):
        raise ValueError("Release renderer/dependency identity mismatch")
    if manifest.get("previous_feed_blobs") != previous_feed_blobs(root, revision):
        raise ValueError("Release prior feed input identity mismatch")
    if manifest.get("accounts_environment") != "production":
        raise ValueError("Release was not built for production account boundaries")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files or manifest.get("content_digest") != digest(canonical(files)):
        raise ValueError("Release file inventory mismatch")
    public = {name.removeprefix("public/"): oid for name, (_, oid) in tracked.items() if name.startswith("public/")}
    if set(files) != set(public) or "deployment.json" in files:
        raise ValueError("Release file set differs from trusted Git public tree")
    if manifest.get("payload_digest") != file_digest(archive) or manifest.get("payload_size") != archive.stat().st_size:
        raise ValueError("Release archive digest/size mismatch")
    if archive.stat().st_size > MAX_PAYLOAD_BYTES:
        raise ValueError("Release archive exceeds the maximum payload size")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Release destination must be empty before verified extraction")
    destination.mkdir(parents=True, exist_ok=True)
    total = 0
    with zipfile.ZipFile(archive) as zip_file:
        names = zip_file.namelist()
        if len(names) != len(set(names)) or set(names) != set(files):
            raise ValueError("Release archive is incomplete or contains extra/duplicate files")
        for info in zip_file.infolist():
            name = info.filename
            file_type = (info.external_attr >> 16) & 0o170000
            if (not safe_path(name) or info.is_dir() or file_type != 0o100000
                    or info.flag_bits & 1 or info.compress_type != zipfile.ZIP_DEFLATED
                    or info.file_size != files[name].get("size")):
                raise ValueError(f"Unsafe or mismatched release member: {name}")
            total += info.file_size
            if total > MAX_PAYLOAD_BYTES:
                raise ValueError("Release expands beyond the maximum payload size")
            data = zip_file.read(info)
            if digest(data) != files[name].get("sha256") or git_blob(data) != public[name] or files[name].get("git_blob") != public[name]:
                raise ValueError(f"Release member differs from trusted Git content: {name}")
            target = destination.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    snapshots = linked_snapshots(root, files, destination)
    if manifest.get("linked_feed_snapshots") != snapshots:
        raise ValueError("Linked-feed input identity mismatch")
    feed_dates = {}
    for name in sorted(files):
        if name.endswith("/feed.xml"):
            channel = ET.fromstring((destination / name).read_bytes()).find("channel")
            feed_dates[name] = channel.findtext("lastBuildDate") if channel is not None else None
    if manifest.get("rendered_feed_dates") != feed_dates:
        raise ValueError("Rendered feed date provenance mismatch")
    return digest(manifest_bytes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--revision", required=True)
    create.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--revision", required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--payload", type=Path, required=True)
    verify.add_argument("--destination", type=Path, required=True)
    verify.add_argument("--allow-unmerged", action="store_true", help="Fixture/PR CI only; never use for deployment")
    args = parser.parse_args()
    try:
        if args.command == "create":
            release_id, _ = create_release(ROOT, args.revision, args.output)
        else:
            release_id = verify_release(ROOT, args.revision, args.manifest.read_bytes(), args.payload,
                                        args.destination, require_main=not args.allow_unmerged)
        print(release_id)
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        print(f"Release artifact rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
