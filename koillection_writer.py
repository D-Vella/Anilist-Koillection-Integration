"""Write access for the Koillection REST API: series (sub-collection) images and descriptions.

A Collection has no built-in description field in Koillection - free-text
info is stored as a custom field ("Datum") attached to the collection. So
"posting a description" means finding or creating a Datum of type
"textarea" on the collection, while the cover image is uploaded straight to
the collection's dedicated image endpoint.
"""
from __future__ import annotations

import logging

from koillection_reader import KoillectionClient

logger = logging.getLogger(__name__)


class KoillectionWriter:
    def __init__(
        self,
        client: KoillectionClient,
        description_label: str = "Description",
        anilist_id_label: str = "AniList ID",
    ):
        self.client = client
        self.description_label = description_label
        self.anilist_id_label = anilist_id_label

    def upload_collection_image(self, collection_id: str, image_bytes: bytes, filename: str) -> None:
        files = {"file": (filename, image_bytes)}
        self.client.request("POST", f"/api/collections/{collection_id}/image", files=files)

    def upsert_collection_description(self, collection_id: str, description: str, overwrite: bool = False) -> bool:
        """Create or update the description custom field on a collection.

        Returns True if a write happened, False if it was skipped because a
        non-empty value already existed and overwrite was False.
        """
        return self._upsert_datum(collection_id, self.description_label, description, "textarea", overwrite)

    def upsert_anilist_id(self, collection_id: str, anilist_id: int) -> bool:
        """Record the AniList id that resolved this series.

        Always overwrites: this is only called after a title search resolved
        (or re-resolved) the series, i.e. any value already on the field
        either didn't exist or failed to resolve on AniList.
        """
        return self._upsert_datum(collection_id, self.anilist_id_label, str(anilist_id), "text", overwrite=True)

    def _upsert_datum(
        self, collection_id: str, label: str, value: str, datum_type: str, overwrite: bool
    ) -> bool:
        existing_data = list(self.client.paginate(f"/api/collections/{collection_id}/data"))
        existing = next((d for d in existing_data if d.get("label") == label), None)

        if existing:
            if existing.get("value") and not overwrite:
                logger.debug("%s already set for collection %s, skipping", label, collection_id)
                return False
            self.client.request(
                "PATCH",
                f"/api/data/{existing['id']}",
                json={"value": value},
                headers={"Content-Type": "application/merge-patch+json"},
            )
            return True

        self.client.request(
            "POST",
            "/api/data",
            json={
                "collection": f"/api/collections/{collection_id}",
                "type": datum_type,
                "label": label,
                "value": value,
            },
        )
        return True
