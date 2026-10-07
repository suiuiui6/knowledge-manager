from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class ConfluencePage:
    page_id: str
    title: str
    url: str
    version: str
    body_text: str
    heading_path: list[str]
    checksum: str


def _strip_html(value: str) -> str:
    text = value.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    chunks: list[str] = []
    in_tag = False
    for char in text:
        if char == "<":
            in_tag = True
            continue
        if char == ">":
            in_tag = False
            continue
        if not in_tag:
            chunks.append(char)
    return " ".join("".join(chunks).split())


def _normalize_page(base_url: str, item: dict[str, Any]) -> ConfluencePage:
    page_id = str(item["id"])
    title = str(item.get("title", "")).strip()
    version = str(item.get("version", {}).get("number", ""))
    body_value = item.get("body", {}).get("storage", {}).get("value", "")
    body_text = _strip_html(str(body_value))
    path = item.get("_links", {}).get("webui", "")
    url = f"{base_url.rstrip('/')}{path}" if path else ""
    heading_path = [part for part in [item.get("space", {}).get("key", ""), title] if part]
    checksum = hashlib.sha256(body_text.encode("utf-8")).hexdigest()
    return ConfluencePage(
        page_id=page_id,
        title=title,
        url=url,
        version=version,
        body_text=body_text,
        heading_path=heading_path,
        checksum=checksum,
    )


class ConfluenceClient:
    def __init__(self, base_url: str, email: str, api_token: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self._auth = (email, api_token)
        self._timeout = timeout

    async def list_pages(
        self,
        space_key: str,
        root_page_id: str = "",
        limit: int = 25,
        cursor: str = "",
    ) -> tuple[list[ConfluencePage], str]:
        params = {
            "spaceKey": space_key,
            "limit": limit,
            "expand": "body.storage,version,space",
        }
        if cursor:
            params["cursor"] = cursor
        if root_page_id:
            params["ancestor"] = root_page_id

        async with httpx.AsyncClient(auth=self._auth, timeout=self._timeout) as client:
            response = await client.get(f"{self.base_url}/rest/api/content", params=params)
            response.raise_for_status()
            payload = response.json()

        pages = [_normalize_page(self.base_url, item) for item in payload.get("results", [])]
        next_cursor = ""
        if payload.get("_links", {}).get("next"):
            next_cursor = str(payload["_links"]["next"])
        return pages, next_cursor
