from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

DRIVE_SCOPES = ("https://www.googleapis.com/auth/drive.readonly",)
FILENAME_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2}) - (?P<title>.+)\.(?P<ext>[^.]+)$")
DRAFT_PREFIXES = ("draft", "_draft", "[draft]", "(draft)", "טיוטה", "_טיוטה")
AUDIO_EXTENSIONS = {"mp3", "m4a", "aac", "wav", "flac", "ogg", "opus"}
VIDEO_EXTENSIONS = {"mp4", "mov", "mkv", "webm", "m4v"}
SUPPORTED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    mime_type: str
    created_time: str
    modified_time: str
    web_view_link: str | None
    size: int | None
    md5_checksum: str | None


@dataclass(frozen=True)
class ParsedDriveFilename:
    published: str
    title: str
    extension: str
    date_source: str


def _drive_timestamp_yyyymmdd(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized).astimezone(timezone.utc).strftime("%Y%m%d")
    except ValueError:
        return None


def _is_draft_filename(name: str) -> bool:
    normalized = name.strip().lower()
    return any(normalized.startswith(prefix) for prefix in DRAFT_PREFIXES)


def parse_drive_filename(name: str, fallback_timestamp: str | None = None) -> ParsedDriveFilename | None:
    if _is_draft_filename(name):
        return None

    match = FILENAME_RE.match(name)
    path = Path(name)
    extension = (match.group("ext") if match else path.suffix.lstrip(".")).lower()
    if extension not in SUPPORTED_EXTENSIONS:
        return None

    if match:
        try:
            published = date.fromisoformat(match.group("date")).strftime("%Y%m%d")
            date_source = "filename"
        except ValueError:
            published = _drive_timestamp_yyyymmdd(fallback_timestamp)
            date_source = "drive"
        title = match.group("title").strip()
    else:
        published = _drive_timestamp_yyyymmdd(fallback_timestamp)
        title = path.stem.strip()
        date_source = "drive"

    if not published:
        return None
    if not title:
        return None
    return ParsedDriveFilename(published=published, title=title, extension=extension, date_source=date_source)


def drive_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(raw),
        scopes=DRIVE_SCOPES,
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def list_drive_files(folder_id: str) -> list[DriveFile]:
    service = drive_service()
    files: list[DriveFile] = []
    page_token = None
    while True:
        response = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields=(
                    "nextPageToken, "
                    "files(id, name, mimeType, createdTime, modifiedTime, webViewLink, size, md5Checksum)"
                ),
                pageToken=page_token,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
            .execute()
        )
        for item in response.get("files", []):
            if item.get("mimeType") == "application/vnd.google-apps.folder":
                continue
            files.append(
                DriveFile(
                    id=item["id"],
                    name=item["name"],
                    mime_type=item.get("mimeType") or "",
                    created_time=item.get("createdTime") or "",
                    modified_time=item.get("modifiedTime") or "",
                    web_view_link=item.get("webViewLink"),
                    size=int(item["size"]) if item.get("size") else None,
                    md5_checksum=item.get("md5Checksum"),
                )
            )
        page_token = response.get("nextPageToken")
        if not page_token:
            return files


def download_drive_file(file_id: str, dest: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload

    service = drive_service()
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as handle:
        downloader = MediaIoBaseDownload(handle, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
