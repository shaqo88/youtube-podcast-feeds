from __future__ import annotations

import argparse
from pathlib import Path

import requests
import urllib3
from PIL import Image, ImageOps

from .config import load_show

HTTP_TIMEOUT = 60
TARGET_SIZE = 1400


def prepare_show_artwork(slug: str, source_url: str, verify_tls: bool = True) -> None:
    show = load_show(slug)
    if not verify_tls:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    response = requests.get(source_url, timeout=HTTP_TIMEOUT, verify=verify_tls)
    response.raise_for_status()

    raw_path = show.show_dir / "assets" / "source-artwork"
    raw_path.mkdir(parents=True, exist_ok=True)
    source_path = raw_path / "original"
    source_path.write_bytes(response.content)

    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image = ImageOps.fit(image, (TARGET_SIZE, TARGET_SIZE), method=Image.Resampling.LANCZOS, centering=(0.5, 0.4))
        show.podcast.artwork_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(show.podcast.artwork_path, "PNG", optimize=True)
    print(f"Wrote {show.podcast.artwork_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--insecure", action="store_true", help="Disable TLS verification for a user-supplied source URL.")
    args = parser.parse_args()
    prepare_show_artwork(args.show, args.source_url, verify_tls=not args.insecure)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
