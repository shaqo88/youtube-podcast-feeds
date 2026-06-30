from __future__ import annotations

import argparse
from urllib.parse import urlsplit, urlunsplit

import requests
import urllib3
from PIL import Image, ImageOps

from .config import load_show

HTTP_TIMEOUT = 60
TARGET_SIZE = 1400
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)


def _artwork_candidates(source_url: str) -> list[str]:
    candidates = [source_url]
    parsed = urlsplit(source_url)
    if parsed.query.startswith(".") and not parsed.path.endswith(parsed.query):
        candidates.append(urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", parsed.fragment)))
    return candidates


def prepare_show_artwork(slug: str, source_url: str, verify_tls: bool = True) -> None:
    show = load_show(slug)
    if not verify_tls:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    response = None
    last_error: Exception | None = None
    for candidate in _artwork_candidates(source_url):
        try:
            response = requests.get(
                candidate,
                headers={"User-Agent": USER_AGENT, "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"},
                timeout=HTTP_TIMEOUT,
                verify=verify_tls,
            )
            response.raise_for_status()
            break
        except requests.RequestException as exc:
            last_error = exc
            response = None
    if response is None:
        raise last_error or RuntimeError(f"Could not download artwork from {source_url}")

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
