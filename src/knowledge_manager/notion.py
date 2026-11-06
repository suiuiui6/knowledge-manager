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


def _extract_block_text(block: dict[str, Any]) -> str:
    block_type = str(block.get("type", ""))
    value = block.get(block_type)
    if not isinstance(value, dict):
        return ""
    rich_text = value.get("rich_text")
    if rich_text:
        return _extract_plain_text(rich_text)
    if "caption" in value:
        return _extract_plain_text(value.get("caption", []))
    if "title" in value:
        return _extract_plain_text(value.get("title", []))
    return ""


class NotionClient:
    def __init__(self, api_token: str, timeout: float = 30.0):
        self._api_token = api_token
        self._timeout = timeout

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await client.request(method, url, json=json_body, params=params)
        response.raise_for_status()
        return response.json()

    async def _fetch_block_children(
        self,
        client: httpx.AsyncClient,
        block_id: str,
    ) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        cursor = ""
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            data = await self._request_json(
                client,
                "GET",
                f"https://api.notion.com/v1/blocks/{block_id}/children",
                params=params,
            )
            blocks.extend(data.get("results", []))
            cursor = str(data.get("next_cursor") or "")
            if not data.get("has_more"):
                break
        return blocks

    async def _collect_block_text(
        self,
        client: httpx.AsyncClient,
        block_id: str,
    ) -> str:
        lines: list[str] = []
        for block in await self._fetch_block_children(client, block_id):
            block_text = _extract_block_text(block).strip()
            if block_text:
                lines.append(block_text)
            if block.get("has_children"):
                nested_text = await self._collect_block_text(client, str(block.get("id", "")))
                if nested_text.strip():
                    lines.append(nested_text.strip())
        return "\n".join(lines).strip()

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
            data = await self._request_json(
                client,
                "POST",
                f"https://api.notion.com/v1/databases/{database_id}/query",
                json_body=payload,
            )
            pages: list[NotionPage] = []
            for item in data.get("results", []):
                page = _normalize_page(item)
                body_text = await self._collect_block_text(client, page.page_id)
                if body_text:
                    page = NotionPage(
                        page_id=page.page_id,
                        title=page.title,
                        url=page.url,
                        version=page.version,
                        body_text=body_text,
                        heading_path=page.heading_path,
                        checksum=hashlib.sha256(body_text.encode("utf-8")).hexdigest(),
                    )
                pages.append(page)
        next_cursor = str(data.get("next_cursor") or "")
        return pages, next_cursor
