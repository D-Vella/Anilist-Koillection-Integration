"""Write access for the Koillection REST API: item images and descriptions.

An Item has no built-in description field in Koillection - free-text info
is stored as a custom field ("Datum") attached to the item. So "posting a
description" means finding or creating a Datum of type "textarea" on the
item, while the cover image is uploaded straight to the item's dedicated
image endpoint.
"""
from __future__ import annotations

import logging

from koillection_reader import KoillectionClient

logger = logging.getLogger(__name__)


class KoillectionWriter:
    def __init__(self, client: KoillectionClient, description_label: str = "Description"):
        self.client = client
        self.description_label = description_label

    def upload_item_image(self, item_id: str, image_bytes: bytes, filename: str) -> None:
        files = {"file": (filename, image_bytes)}
        self.client.request("POST", f"/api/items/{item_id}/image", files=files)

    def upsert_description(self, item_id: str, description: str, overwrite: bool = False) -> bool:
        """Create or update the description custom field on an item.

        Returns True if a write happened, False if it was skipped because a
        non-empty value already existed and overwrite was False.
        """
        existing_data = list(self.client.paginate(f"/api/items/{item_id}/data"))
        existing = next((d for d in existing_data if d.get("label") == self.description_label), None)

        if existing:
            if existing.get("value") and not overwrite:
                logger.debug("Description already set for item %s, skipping", item_id)
                return False
            self.client.request(
                "PATCH",
                f"/api/data/{existing['id']}",
                json={"value": description},
                headers={"Content-Type": "application/merge-patch+json"},
            )
            return True

        self.client.request(
            "POST",
            "/api/data",
            json={
                "item": f"/api/items/{item_id}",
                "type": "textarea",
                "label": self.description_label,
                "value": description,
            },
        )
        return True
