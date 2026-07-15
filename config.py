"""Environment-driven configuration for the AniList -> Koillection sync."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value else default


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    koillection_base_url: str
    koillection_username: str
    koillection_password: str
    koillection_collection: str
    description_label: str
    anilist_id_label: str
    anilist_api_url: str
    anilist_request_delay: float
    overwrite_existing: bool
    dry_run: bool
    request_timeout: float

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            koillection_base_url=_require("KOILLECTION_BASE_URL").rstrip("/"),
            koillection_username=_require("KOILLECTION_USERNAME"),
            koillection_password=_require("KOILLECTION_PASSWORD"),
            koillection_collection=_require("KOILLECTION_COLLECTION"),
            description_label=os.getenv("KOILLECTION_DESCRIPTION_LABEL", "Description"),
            anilist_id_label=os.getenv("KOILLECTION_ANILIST_ID_LABEL", "AniList ID"),
            anilist_api_url=os.getenv("ANILIST_API_URL", "https://graphql.anilist.co"),
            anilist_request_delay=_env_float("ANILIST_REQUEST_DELAY", 2.0),
            overwrite_existing=_env_bool("OVERWRITE_EXISTING", False),
            dry_run=_env_bool("DRY_RUN", False),
            request_timeout=_env_float("REQUEST_TIMEOUT", 15.0),
        )
