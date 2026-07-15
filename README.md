# Anilist-Koillection-Integration
A simple script to pull data from Ani List into Koillection based on multiple series.

Anilist API Documentation:
https://docs.anilist.co/guide/introduction

Koillection API Documentation.
https://github.com/benjaminjonard/koillection/wiki/API

## How it works

This expects a Koillection layout where a parent collection (e.g. "Manga")
has one sub-collection per series (e.g. "Manga/Fly Me to the Moon"), with
owned volumes stored as items inside each series. AniList only has metadata
at the series level, not per-volume, so for every child collection of the
configured parent the script searches AniList for a matching manga and
writes back onto that **series collection**:

- its cover image, via the collection's image upload endpoint
- a description built by concatenating the AniList synopsis, the average
  score and status, and a footer noting the retrieval date, e.g.:

  ```
  A slice-of-life romantic comedy about two co-workers...

  Score: 78/100 | Status: Finished

  Data from AniList API retrieved 2026-07-15
  ```

A description doesn't exist as a built-in field on a Koillection
collection, so it's stored as a custom field ("Datum") with the label
configured by `KOILLECTION_DESCRIPTION_LABEL`.

The project is split into four files:

| File                    | Responsibility                                                        |
|--------------------------|------------------------------------------------------------------------|
| `koillection_reader.py`  | JWT auth + reading a parent collection and its child series from Koillection |
| `anilist_client.py`      | Searching AniList and fetching description/score/status/cover image    |
| `koillection_writer.py`  | Uploading the series cover image and upserting the description field   |
| `main.py`                | Control script that ties the three together                           |

`config.py` loads settings from a `.env` file (see `.env.example`).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your Koillection instance URL/credentials and collection name
```

## Usage

```bash
python main.py                 # interactive: confirm ambiguous AniList matches
python main.py --yes           # accept the best AniList match automatically
python main.py --limit 5 -v    # dry-run friendly test on a handful of series
```

Set `DRY_RUN=true` in `.env` to preview what would change without writing
anything, and `OVERWRITE_EXISTING=true` to replace images/descriptions that
are already set. When a title match isn't confident, the script lists the
candidate AniList results and lets you pick one (or skip) rather than
guessing, unless `--yes` is passed.
