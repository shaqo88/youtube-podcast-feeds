from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

HTTP_TIMEOUT = 20
NETWORK_WORKERS = 4
USER_AGENT = "torah-pod-availability/1.0"


class AvailabilityError(ValueError):
    pass


def notification_transition(current: str, previous: str) -> str:
    if current == "failure" and previous != "failure":
        return "failure"
    if current == "success" and previous == "failure":
        return "recovery"
    return "none"


def _response(
    url: str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    request_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=HTTP_TIMEOUT) as response:
        read_limit = 2 if "Range" in request_headers else 10 * 1024 * 1024 + 1
        return (
            int(response.status),
            {key.lower(): value for key, value in response.headers.items()},
            response.read(read_limit),
        )


def _required_https_url(value: str, label: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise AvailabilityError(f"invalid_{label}_url")
    return value


def parse_latest_enclosure(feed_body: bytes) -> dict[str, str | int]:
    try:
        root = ET.fromstring(feed_body)
    except ET.ParseError as exc:
        raise AvailabilityError("invalid_feed_xml") from exc
    channel = root.find("channel")
    if channel is None:
        raise AvailabilityError("missing_feed_channel")
    items = channel.findall("item")
    if not items:
        raise AvailabilityError("empty_feed")
    latest = items[0]
    enclosure = latest.find("enclosure")
    if enclosure is None:
        raise AvailabilityError("missing_latest_enclosure")
    enclosure_url = _required_https_url(
        str(enclosure.get("url") or ""),
        "enclosure",
    )
    enclosure_type = str(enclosure.get("type") or "").lower()
    if not enclosure_type.startswith("audio/"):
        raise AvailabilityError("invalid_enclosure_type")

    def node_text(name: str) -> str:
        node = latest.find(name)
        return (node.text or "").strip() if node is not None else ""

    return {
        "item_count": len(items),
        "title": node_text("title"),
        "guid": node_text("guid"),
        "published": node_text("pubDate"),
        "enclosure_url": enclosure_url,
        "enclosure_type": enclosure_type,
    }


ResponseReader = Callable[..., tuple[int, dict[str, str], bytes]]


def check_show(
    show: dict[str, Any],
    *,
    response_reader: ResponseReader = _response,
) -> dict[str, Any]:
    slug = str(show.get("slug") or "")
    feed_url = _required_https_url(str(show.get("feed_url") or ""), "feed")
    result: dict[str, Any] = {
        "slug": slug,
        "feed_url": feed_url,
        "status": "error",
        "feed_status": None,
        "enclosure_status": None,
        "range_supported": False,
    }
    try:
        feed_status, feed_headers, feed_body = response_reader(feed_url)
        result["feed_status"] = feed_status
        if feed_status != 200:
            raise AvailabilityError("feed_http_error")
        content_type = feed_headers.get("content-type", "").lower()
        if content_type and not any(value in content_type for value in ("xml", "rss")):
            raise AvailabilityError("invalid_feed_content_type")
        latest = parse_latest_enclosure(feed_body)
        result["latest_episode"] = latest

        enclosure_status, enclosure_headers, enclosure_body = response_reader(
            str(latest["enclosure_url"]),
            headers={"Range": "bytes=0-0"},
        )
        result["enclosure_status"] = enclosure_status
        if enclosure_status != 206:
            raise AvailabilityError("enclosure_range_http_error")
        if not enclosure_headers.get("content-range", "").startswith("bytes 0-0/"):
            raise AvailabilityError("invalid_content_range")
        if not enclosure_headers.get("content-type", "").lower().startswith("audio/"):
            raise AvailabilityError("invalid_enclosure_content_type")
        if len(enclosure_body) != 1:
            raise AvailabilityError("invalid_range_body")
        result["range_supported"] = True
        result["status"] = "ok"
        return result
    except AvailabilityError as exc:
        result["error"] = str(exc)
        return result
    except HTTPError as exc:
        result["error"] = "http_error"
        result["http_status"] = exc.code
        return result
    except (OSError, URLError, TimeoutError):
        result["error"] = "network_error"
        return result


def check_catalog(
    catalog: list[dict[str, Any]],
    *,
    host_prefix: str,
    response_reader: ResponseReader = _response,
) -> dict[str, Any]:
    selected = [
        item
        for item in catalog
        if str(item.get("feed_url") or "").startswith(host_prefix)
    ]
    if not selected:
        raise AvailabilityError("no_matching_feeds")
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=NETWORK_WORKERS) as executor:
        futures = {
            executor.submit(check_show, item, response_reader=response_reader): item
            for item in selected
        }
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: str(item["slug"]))
    failures = sum(item["status"] != "ok" for item in results)
    return {
        "status": "ok" if failures == 0 else "error",
        "checked_shows": len(results),
        "failed_shows": failures,
        "shows": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("public/catalog.json"))
    parser.add_argument("--host-prefix", default="https://torah-pod.pages.dev/")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
        if not isinstance(catalog, list):
            raise AvailabilityError("invalid_catalog")
        report = check_catalog(catalog, host_prefix=args.host_prefix)
    except (AvailabilityError, OSError, json.JSONDecodeError) as exc:
        report = {
            "status": "error",
            "checked_shows": 0,
            "failed_shows": 0,
            "error": str(exc),
            "shows": [],
        }

    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
