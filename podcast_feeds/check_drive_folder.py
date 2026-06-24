from __future__ import annotations

import argparse
import re
import sys

from .drive import list_drive_files, parse_drive_filename

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

FOLDER_ID_RE = re.compile(r"/folders/([^/?#]+)")


def folder_id_from_input(value: str) -> str:
    value = value.strip()
    match = FOLDER_ID_RE.search(value)
    if match:
        return match.group(1)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True, help="Google Drive folder URL or folder ID.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum files to print.")
    args = parser.parse_args()

    folder_id = folder_id_from_input(args.folder)
    files = list_drive_files(folder_id)
    matched = []
    skipped = []
    for file in files:
        parsed = parse_drive_filename(file.name)
        if parsed:
            matched.append((file, parsed))
        else:
            skipped.append(file)

    print(f"Folder ID: {folder_id}")
    print(f"Files found: {len(files)}")
    print(f"Publishable files: {len(matched)}")
    print(f"Skipped draft/unsupported files: {len(skipped)}")

    if matched:
        print("\nPublishable:")
        for file, parsed in matched[: args.limit]:
            print(f"- {parsed.published} | {parsed.title} | {parsed.extension} | {file.name}")

    if skipped:
        print("\nSkipped:")
        for file in skipped[: args.limit]:
            print(f"- {file.name}")

    if not files:
        print("\nNo files found. Check that the folder is shared with the service account.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
