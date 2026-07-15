# Anilist-Koillection-Integration
A simple script to pull data from Ani List into Koillection based on multiple series.

Anilist API Documentation:
https://docs.anilist.co/guide/introduction

Koillection API Documentation.
https://github.com/benjaminjonard/koillection/wiki/API

## How it works

For every item in a chosen Koillection collection (manga, to start), the
script searches AniList for a matching manga and writes its cover image and
description back onto the Koillection item. A description doesn't exist as
a built-in field on a Koillection item, so it's stored as a custom field
("Datum") with the label configured by `KOILLECTION_DESCRIPTION_LABEL`.

The project is split into four files:

| File                    | Responsibility                                                |
|--------------------------|----------------------------------------------------------------|
| `koillection_reader.py`  | JWT auth + reading a collection and its items from Koillection |
| `anilist_client.py`      | Searching AniList and fetching manga description/cover image   |
| `koillection_writer.py`  | Uploading the item image and upserting the description field   |
| `main.py`                | Control script that ties the three together                    |

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
python main.py --limit 5 -v    # dry-run friendly test on a handful of items
```

Set `DRY_RUN=true` in `.env` to preview what would change without writing
anything, and `OVERWRITE_EXISTING=true` to replace images/descriptions that
are already set. When a title match isn't confident, the script lists the
candidate AniList results and lets you pick one (or skip) rather than
guessing, unless `--yes` is passed.
