"""Control script: syncs a Koillection collection with AniList manga metadata.

For every item in the configured Koillection collection, this looks up a
matching manga on AniList and writes its cover image and description back
to the item. Configure the .env file (see .env.example) before running:

    python main.py
    python main.py --yes            # accept the best AniList match automatically
    python main.py --limit 5 -v     # try it on a handful of items first
"""
from __future__ import annotations

import argparse
import logging
import sys

from anilist_client import AnilistClient, MangaMatch
from config import Settings
from koillection_reader import KoillectionClient, KoillectionReader
from koillection_writer import KoillectionWriter

logger = logging.getLogger("sync")

AUTO_MATCH_THRESHOLD = 0.9


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync a Koillection collection with AniList manga data.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Accept the best AniList match automatically instead of asking for confirmation.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N items (for testing).")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args()


def choose_match(item_name: str, matches: list[MangaMatch], auto: bool) -> MangaMatch | None:
    if not matches:
        logger.warning("No AniList results for %r", item_name)
        return None

    best = matches[0]
    if auto or best.score >= AUTO_MATCH_THRESHOLD:
        return best

    print(f"\nItem: {item_name}")
    for i, match in enumerate(matches, start=1):
        print(f"  [{i}] {match.title}  (match score {match.score:.2f})  {match.site_url}")
    print("  [s] skip this item")

    choice = input("Pick a match: ").strip().lower()
    if choice in ("s", ""):
        return None
    try:
        index = int(choice) - 1
        if 0 <= index < len(matches):
            return matches[index]
    except ValueError:
        pass

    logger.warning("Invalid selection %r, skipping item", choice)
    return None


def sync_item(
    item: dict,
    reader: KoillectionReader,
    writer: KoillectionWriter,
    anilist: AnilistClient,
    settings: Settings,
    auto_match: bool,
) -> bool:
    name = item.get("name", "")
    item_id = item["id"]

    matches = anilist.search_manga(name)
    match = choose_match(name, matches, auto=auto_match)
    if match is None:
        return False

    if settings.dry_run:
        logger.info("[dry-run] Would update %r with AniList match %r", name, match.title)
        return True

    needs_image = settings.overwrite_existing or not item.get("image")
    if needs_image and match.cover_image_url:
        image_bytes = anilist.download_cover_image(match)
        if image_bytes:
            filename = match.cover_image_url.rsplit("/", 1)[-1] or f"{match.id}.jpg"
            writer.upload_item_image(item_id, image_bytes, filename)

    if match.description:
        writer.upsert_description(item_id, match.description, overwrite=settings.overwrite_existing)
    else:
        logger.warning("AniList match %r has no description to write", match.title)

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
    writer = KoillectionWriter(client, description_label=settings.description_label)
    anilist = AnilistClient(
        api_url=settings.anilist_api_url,
        request_delay=settings.anilist_request_delay,
        timeout=settings.request_timeout,
    )

    updated = skipped = failed = 0

    #Get Parent Collection:
    parent_collection = reader.get_collection(settings.koillection_collection)

    #Get Child Collections:
    child_collections = reader.list_child_collections(parent_collection["id"])

    for child_collection in child_collections:
        logger.info("Syncing child collection %r (%s)", child_collection.get("title"), child_collection["id"])

        collection = reader.get_collection(child_collection["id"])
        logger.info("Syncing collection %r (%s)", collection.get("title"), collection["id"])

        items = reader.list_items(collection["id"])
        if args.limit:
            items = items[: args.limit]
        logger.info("Found %d item(s) to process", len(items))

        for item in items:
            try:
                if sync_item(item, reader, writer, anilist, settings, auto_match=args.yes):
                    updated += 1
                else:
                    skipped += 1
            except Exception:
                logger.exception("Failed to sync item %r", item.get("name"))
                failed += 1

    logger.info("Done. updated=%d skipped=%d failed=%d", updated, skipped, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
