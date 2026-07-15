"""Authentication and read access for the Koillection REST API.

Koillection is built on API Platform: resources are fetched as JSON, JWT
auth is obtained via ``POST /api/authentication_token`` and reused as a
Bearer token, and collection endpoints are paginated with a ``page`` query
parameter. ``KoillectionClient`` handles that plumbing; ``KoillectionReader``
adds the read-oriented convenience methods this project needs.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Iterator

import requests

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F-]{27}$")


class KoillectionClient:
    """Shared session, auth and request helpers used by reader and writer."""

    def __init__(self, base_url: str, username: str, password: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        self._token: str | None = None

    def _login(self) -> str:
        response = self.session.post(
            f"{self.base_url}/api/authentication_token",
            json={"username": self.username, "password": self.password},
            timeout=self.timeout,
        )
        response.raise_for_status()
        token = response.json().get("token")
        if not token:
            raise RuntimeError("Koillection login response did not include a token")
        return token

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"
        extra_headers = kwargs.pop("headers", None) or {}

        if self._token is None:
            self._token = self._login()

        def send() -> requests.Response:
            headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
            headers.update(extra_headers)
            return self.session.request(method, url, headers=headers, timeout=self.timeout, **kwargs)

        response = send()
        if response.status_code == 401:
            # Token likely expired - re-authenticate once and retry.
            self._token = self._login()
            response = send()

        response.raise_for_status()
        return response

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params).json()

    def paginate(self, path: str, params: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        """Yield every member of a Koillection collection endpoint, walking pages."""
        page = 1
        params = dict(params or {})
        while True:
            params["page"] = page
            data = self.get_json(path, params=params)
            items = data.get("hydra:member", data.get("member")) if isinstance(data, dict) else data
            if not items:
                break
            yield from items
            page += 1


class KoillectionReader:
    """Read-only operations: finding a collection and listing its items."""

    def __init__(self, client: KoillectionClient):
        self.client = client

    def get_collection(self, name_or_id: str) -> dict[str, Any]:
        """Look up a collection by UUID, or by exact (case-insensitive) title."""
        if _UUID_RE.match(name_or_id):
            return self.client.get_json(f"/api/collections/{name_or_id}")

        for collection in self.client.paginate("/api/collections"):
            if collection.get("title", "").strip().lower() == name_or_id.strip().lower():
                return collection

        raise LookupError(f"No Koillection collection titled {name_or_id!r} was found")

    def list_items(self, collection_id: str) -> list[dict[str, Any]]:
        return list(self.client.paginate(f"/api/collections/{collection_id}/items"))

    def list_item_data(self, item_id: str) -> list[dict[str, Any]]:
        return list(self.client.paginate(f"/api/items/{item_id}/data"))
