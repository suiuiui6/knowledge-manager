from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class NotionPage:
    page_id: str
    title: str
    url: str
    version: str
    body_text: str
    heading_path: list[str]
    checksum: str


def _extract_plain_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_extract_plain_text(item) for item in value).strip()
    if isinstance(value, dict):
        if "plain_text" in value:
            return str(value["plain_text"])
        if "text" in value and isinstance(value["text"], dict):
            content = value["text"].get("content")
            if content:
                return str(content)
        return " ".join(_extract_plain_text(item) for item in value.values()).strip()
    return ""


def _normalize_page(item: dict[str, Any]) -> NotionPage:
    page_id = str(item["id"])
    properties = item.get("properties", {})
    title = page_id
    for prop in properties.values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            title_value = _extract_plain_text(prop.get("title", []))
            if title_value.strip():
                title = title_value.strip()
                break
        if isinstance(prop, dict) and "title" in prop:
            title_value = _extract_plain_text(prop.get("title", []))
            if title_value.strip():
                title = title_value.strip()
                break
    body_text = _extract_plain_text(item.get("rich_text", []))
    if not body_text:
        body_text = _extract_plain_text(item.get("plain_text", ""))
    version = str(item.get("last_edited_time", ""))
    checksum = hashlib.sha256(body_text.encode("utf-8")).hexdigest()
    return NotionPage(
        page_id=page_id,
        title=title,
        url=str(item.get("url", "")),
        version=version,
        body_text=body_text,
        heading_path=["Notion", title] if title else ["Notion"],
        checksum=checksum,
    )


class NotionClient:
    def __init__(self, api_token: str, timeout: float = 30.0):
        self._api_token = api_token
        self._timeout = timeout

    async def list_pages(
        self,
        database_id: str,
        page_limit: int = 25,
        cursor: str = "",
    ) -> tuple[list[NotionPage], str]:
        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {"page_size": page_limit}
        if cursor:
            payload["start_cursor"] = cursor

        async with httpx.AsyncClient(timeout=self._timeout, headers=headers) as client:
            response = await client.post(
                f"https://api.notion.com/v1/databases/{database_id}/query",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        pages = [_normalize_page(item) for item in data.get("results", [])]
        next_cursor = str(data.get("next_cursor") or "")
        return pages, next_cursor
