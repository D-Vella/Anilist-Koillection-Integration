"""Client for looking up manga metadata from the AniList GraphQL API.

Docs: https://docs.anilist.co/guide/introduction
AniList enforces a per-minute rate limit and answers with 429 + a
Retry-After header when it is exceeded, so every request is throttled and
429s are retried with backoff rather than treated as fatal.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher

import requests

logger = logging.getLogger(__name__)

SEARCH_QUERY = """
query ($search: String, $perPage: Int) {
  Page(page: 1, perPage: $perPage) {
    media(search: $search, type: MANGA, sort: SEARCH_MATCH) {
      id
      title { romaji english native }
      description(asHtml: false)
      coverImage { extraLarge large }
      siteUrl
    }
  }
}
"""

_TAG_RE = re.compile(r"<[^>]+>")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_INLINE_SPACE_RE = re.compile(r"[ \t]+")
_WORD_RE = re.compile(r"[^a-z0-9]+")


def clean_description(text: str | None) -> str:
    """Strip the stray HTML tags AniList descriptions commonly contain."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = text.replace("\r\n", "\n")
    text = _INLINE_SPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def _best_title(title_obj: dict) -> str:
    title_obj = title_obj or {}
    return title_obj.get("english") or title_obj.get("romaji") or title_obj.get("native") or ""


def _similarity(a: str, b: str) -> float:
    normalize = lambda s: _WORD_RE.sub(" ", s.lower()).strip()
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


@dataclass
class MangaMatch:
    id: int
    title: str
    description: str
    cover_image_url: str | None
    site_url: str
    score: float


class AnilistClient:
    def __init__(
        self,
        api_url: str = "https://graphql.anilist.co",
        request_delay: float = 2.0,
        timeout: float = 15.0,
    ):
        self.api_url = api_url
        self.request_delay = request_delay
        self.timeout = timeout
        self.session = requests.Session()
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)

    def _post(self, query: str, variables: dict, max_retries: int = 4) -> dict:
        for attempt in range(max_retries):
            self._throttle()
            response = self.session.post(
                self.api_url, json={"query": query, "variables": variables}, timeout=self.timeout
            )
            self._last_request_at = time.monotonic()

            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", 5))
                logger.warning("AniList rate limit hit, waiting %.1fs (attempt %d)", retry_after, attempt + 1)
                time.sleep(retry_after)
                continue

            response.raise_for_status()
            payload = response.json()
            if payload.get("errors"):
                raise RuntimeError(f"AniList API error: {payload['errors']}")
            return payload["data"]

        raise RuntimeError("AniList API rate limit retries exhausted")

    def search_manga(self, title: str, limit: int = 5) -> list[MangaMatch]:
        """Return candidate manga for a title, best match first."""
        data = self._post(SEARCH_QUERY, {"search": title, "perPage": limit})
        media = data.get("Page", {}).get("media", [])

        matches = []
        for entry in media:
            entry_title = _best_title(entry.get("title"))
            cover = entry.get("coverImage") or {}
            matches.append(
                MangaMatch(
                    id=entry["id"],
                    title=entry_title,
                    description=clean_description(entry.get("description")),
                    cover_image_url=cover.get("extraLarge") or cover.get("large"),
                    site_url=entry.get("siteUrl", ""),
                    score=_similarity(title, entry_title),
                )
            )

        matches.sort(key=lambda m: m.score, reverse=True)
        return matches

    def download_cover_image(self, match: MangaMatch) -> bytes | None:
        if not match.cover_image_url:
            return None
        response = self.session.get(match.cover_image_url, timeout=self.timeout)
        response.raise_for_status()
        return response.content
