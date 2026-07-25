"""Collect AI news from public RSS and Atom feeds."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree


FEEDS = {
    "NVIDIA AI Blog": "https://blogs.nvidia.com/feed/",
    "Hugging Face Blog": "https://huggingface.co/blog/feed.xml",
}
OUTPUT_DIRECTORY = Path(__file__).resolve().parent.parent / "data" / "raw"
REQUEST_TIMEOUT_SECONDS = 20
MAX_ITEMS_PER_FEED = 20


class NewsCollectionError(RuntimeError):
    """Raised when AI news cannot be collected or saved."""


def _element_text(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return unescape("".join(element.itertext())).strip()


def _first_child(
    element: ElementTree.Element, names: tuple[str, ...]
) -> ElementTree.Element | None:
    for child in element:
        local_name = child.tag.rsplit("}", 1)[-1]
        if local_name in names:
            return child
    return None


def _normalize_timestamp(value: str) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _entry_url(entry: ElementTree.Element) -> str:
    link = _first_child(entry, ("link",))
    if link is None:
        return ""
    return (link.get("href") or _element_text(link)).strip()


def parse_feed(xml_data: bytes, source: str) -> list[dict[str, Any]]:
    """Parse RSS or Atom XML into the shared news item format."""
    try:
        root = ElementTree.fromstring(xml_data)
    except ElementTree.ParseError as exc:
        raise NewsCollectionError(f"{source} returned invalid XML: {exc}") from exc

    entries = [
        element
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] in {"item", "entry"}
    ]
    articles: list[dict[str, Any]] = []

    for entry in entries[:MAX_ITEMS_PER_FEED]:
        title = _element_text(_first_child(entry, ("title",)))
        url = _entry_url(entry)
        if not title or not url:
            continue

        published = _element_text(
            _first_child(entry, ("pubDate", "published", "updated"))
        )
        summary = _element_text(
            _first_child(entry, ("description", "summary", "content"))
        )
        articles.append(
            {
                "source": source,
                "title": title,
                "url": url,
                "published_at": _normalize_timestamp(published),
                "summary": summary,
            }
        )

    return articles


def collect_ai_news() -> dict[str, Any]:
    """Fetch configured free feeds and return normalized AI news."""
    collected_at = datetime.now(timezone.utc).isoformat()
    articles: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for source, feed_url in FEEDS.items():
        request = Request(
            feed_url,
            headers={
                "Accept": "application/rss+xml, application/atom+xml, application/xml",
                "User-Agent": "AI-Web3-Lab/1.0",
            },
        )
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                articles.extend(parse_feed(response.read(), source))
        except HTTPError as exc:
            errors.append({"source": source, "error": f"HTTP {exc.code}"})
        except URLError as exc:
            errors.append({"source": source, "error": str(exc.reason)})
        except (TimeoutError, NewsCollectionError) as exc:
            errors.append({"source": source, "error": str(exc)})

    unique_articles = list({article["url"]: article for article in articles}.values())
    if not unique_articles:
        details = "; ".join(
            f"{item['source']}: {item['error']}" for item in errors
        )
        raise NewsCollectionError(f"No AI news was collected. {details}".strip())

    return {
        "category": "ai_news",
        "collected_at": collected_at,
        "article_count": len(unique_articles),
        "articles": unique_articles,
        "errors": errors,
    }


def save_ai_news(news_data: dict[str, Any]) -> Path:
    """Save AI news to a UTC date-stamped JSON file."""
    date_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_path = OUTPUT_DIRECTORY / f"ai_news_{date_stamp}.json"
    try:
        OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as output_file:
            json.dump(news_data, output_file, ensure_ascii=False, indent=2)
            output_file.write("\n")
    except OSError as exc:
        raise NewsCollectionError(f"Unable to save AI news: {exc}") from exc
    return output_path


def main() -> int:
    """Collect AI news and save it locally."""
    try:
        output_path = save_ai_news(collect_ai_news())
    except NewsCollectionError as exc:
        print(f"AI news collection failed: {exc}", file=sys.stderr)
        return 1
    print(f"AI news saved to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
