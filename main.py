"""Control script: syncs Koillection series collections with AniList manga metadata.

Koillection layout expected: a parent collection (e.g. "Manga") whose direct
children are one sub-collection per series (e.g. "Manga/Fly Me to the
Moon"), with owned volumes as items inside each series. AniList only has
metadata at the series level, so for every child collection this looks up
the matching manga on AniList and writes its cover image and a description
(AniList synopsis + score + status + a retrieval footer) onto that series
collection.

Some titles are ambiguous on AniList (multiple series share a name), so
each series collection can carry an "AniList ID" custom field. If it's set,
that exact AniList entry is used directly; if it's missing or no longer
resolves, the script falls back to a title search and writes the id it
picked back into that field so future runs skip the search. If a search
ever picks the wrong series, just edit the AniList ID field by hand.

Configure the .env file (see .env.example) before running:

    python main.py
    python main.py --yes            # accept the best AniList match automatically
    python main.py --limit 5 -v     # try it on a handful of series first
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from anilist_client import AnilistClient, MangaMatch, format_status
from config import Settings
from koillection_reader import KoillectionClient, KoillectionReader
from koillection_writer import KoillectionWriter

logger = logging.getLogger("sync")

AUTO_MATCH_THRESHOLD = 0.9


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Koillection series collections with AniList manga data.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Accept the best AniList match automatically instead of asking for confirmation.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N series (for testing).")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args()


def choose_match(series_name: str, matches: list[MangaMatch], auto: bool) -> MangaMatch | None:
    if not matches:
        logger.warning("No AniList results for %r", series_name)
        return None

    best = matches[0]
    if auto or best.score >= AUTO_MATCH_THRESHOLD:
        return best

    print(f"\nSeries: {series_name}")
    for i, match in enumerate(matches, start=1):
        print(f"  [{i}] {match.title}  (match score {match.score:.2f})  {match.site_url}")
    print("  [s] skip this series")

    choice = input("Pick a match: ").strip().lower()
    if choice in ("s", ""):
        return None
    try:
        index = int(choice) - 1
        if 0 <= index < len(matches):
            return matches[index]
    except ValueError:
        pass

    logger.warning("Invalid selection %r, skipping series", choice)
    return None


def build_description(match: MangaMatch) -> str:
    """Concatenate the AniList synopsis, score/status and a retrieval footer."""
    parts = [match.description or "No description available."]

    facts = []
    if match.average_score is not None:
        facts.append(f"Score: {match.average_score}/100")
    status_label = format_status(match.status)
    if status_label:
        facts.append(f"Status: {status_label}")
    if facts:
        parts.append(" | ".join(facts))

    parts.append(f"Data from AniList API retrieved {date.today().isoformat()}")
    return "\n\n".join(parts)


def resolve_anilist_id(existing_data: list[dict], label: str) -> int | None:
    datum = next((d for d in existing_data if d.get("label") == label), None)
    value = (datum or {}).get("value")
    if not value:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        logger.warning("%r field contains a non-numeric value %r, ignoring", label, value)
        return None


def sync_series(
    series_collection: dict,
    reader: KoillectionReader,
    writer: KoillectionWriter,
    anilist: AnilistClient,
    settings: Settings,
    auto_match: bool,
) -> bool:
    name = series_collection.get("title", "")
    collection_id = series_collection["id"]

    existing_data = reader.list_collection_data(collection_id)
    anilist_id = resolve_anilist_id(existing_data, settings.anilist_id_label)

    match = anilist.get_manga_by_id(anilist_id) if anilist_id is not None else None
    if anilist_id is not None and match is None:
        logger.warning("%r's AniList ID %s did not resolve, falling back to title search", name, anilist_id)

    needs_id_write = match is None
    if match is None:
        matches = anilist.search_manga(name)
        match = choose_match(name, matches, auto=auto_match)
        if match is None:
            return False

    if settings.dry_run:
        logger.info("[dry-run] Would update %r with AniList match %r (#%s)", name, match.title, match.id)
        return True

    needs_image = settings.overwrite_existing or not series_collection.get("image")
    if needs_image and match.cover_image_url:
        image_bytes = anilist.download_cover_image(match)
        if image_bytes:
            filename = match.cover_image_url.rsplit("/", 1)[-1] or f"{match.id}.jpg"
            writer.upload_collection_image(collection_id, image_bytes, filename)

    description = build_description(match)
    writer.upsert_collection_description(collection_id, description, overwrite=settings.overwrite_existing)

    if needs_id_write:
        writer.upsert_anilist_id(collection_id, match.id)

    logger.info("Updated %r <- AniList #%s %r", name, match.id, match.title)
    return True


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    settings = Settings.load()

    client = KoillectionClient(
        base_url=settings.koillection_base_url,
        username=settings.koillection_username,
        password=settings.koillection_password,
        timeout=settings.request_timeout,
    )
    reader = KoillectionReader(client)
    writer = KoillectionWriter(
        client, description_label=settings.description_label, anilist_id_label=settings.anilist_id_label
    )
    anilist = AnilistClient(
        api_url=settings.anilist_api_url,
        request_delay=settings.anilist_request_delay,
        timeout=settings.request_timeout,
    )

    parent = reader.get_collection(settings.koillection_collection)
    logger.info("Syncing series under %r (%s)", parent.get("title"), parent["id"])

    series_list = reader.list_child_collections(parent["id"])
    if args.limit:
        series_list = series_list[: args.limit]
    logger.info("Found %d series to process", len(series_list))

    updated = skipped = failed = 0
    for series_collection in series_list:
        try:
            if sync_series(series_collection, reader, writer, anilist, settings, auto_match=args.yes):
                updated += 1
            else:
                skipped += 1
        except Exception:
            logger.exception("Failed to sync series %r", series_collection.get("title"))
            failed += 1

    logger.info("Done. updated=%d skipped=%d failed=%d", updated, skipped, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
