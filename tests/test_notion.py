from knowledge_manager.notion import NotionClient, _normalize_page


def test_normalize_page_extracts_title_and_url():
    page = _normalize_page(
        {
            "id": "page-1",
            "last_edited_time": "2026-06-10T08:00:00.000Z",
            "properties": {
                "Name": {
                    "type": "title",
                    "title": [{"plain_text": "Runbook"}],
                }
            },
            "url": "https://www.notion.so/page-1",
        }
    )

    assert page.page_id == "page-1"
    assert page.title == "Runbook"
    assert page.url == "https://www.notion.so/page-1"
    assert page.version == "2026-06-10T08:00:00.000Z"


async def test_notion_client_normalizes_pages(monkeypatch):
    payload = {
        "results": [
            {
                "id": "page-1",
                "last_edited_time": "2026-06-10T08:00:00.000Z",
                "properties": {
                    "Name": {
                        "type": "title",
                        "title": [{"plain_text": "Runbook"}],
                    }
                },
                "url": "https://www.notion.so/page-1",
            }
        ],
        "next_cursor": "cursor-2",
    }

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def request(self, method, url, json=None, params=None):
            if method == "POST":
                return FakeResponse()
            return FakeResponse()

    monkeypatch.setattr("knowledge_manager.notion.httpx.AsyncClient", FakeAsyncClient)

    client = NotionClient("secret")
    pages, next_cursor = await client.list_pages("db-1", page_limit=10)

    assert len(pages) == 1
    assert pages[0].page_id == "page-1"
    assert pages[0].title == "Runbook"
    assert next_cursor == "cursor-2"


async def test_notion_client_fetches_page_body_from_blocks(monkeypatch):
    query_payload = {
        "results": [
            {
                "id": "page-1",
                "last_edited_time": "2026-06-10T08:00:00.000Z",
                "properties": {
                    "Name": {
                        "type": "title",
                        "title": [{"plain_text": "Runbook"}],
                    }
                },
                "url": "https://www.notion.so/page-1",
            }
        ],
        "next_cursor": None,
    }
    block_payloads = {
        "https://api.notion.com/v1/blocks/page-1/children": {
            "results": [
                {
                    "id": "block-1",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"plain_text": "Primary runbook body"}],
                    },
                    "has_children": False,
                },
                {
                    "id": "block-2",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"plain_text": "Escalate to on-call"}],
                    },
                    "has_children": True,
                },
            ],
            "has_more": False,
            "next_cursor": None,
        },
        "https://api.notion.com/v1/blocks/block-2/children": {
            "results": [
                {
                    "id": "block-2a",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"plain_text": "Nested child guidance"}],
                    },
                    "has_children": False,
                }
            ],
            "has_more": False,
            "next_cursor": None,
        },
    }

    class FakeResponse:
        def __init__(self, payload) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def request(self, method, url, json=None, params=None):
            if method == "POST":
                return FakeResponse(query_payload)
            return FakeResponse(block_payloads[url])

    monkeypatch.setattr("knowledge_manager.notion.httpx.AsyncClient", FakeAsyncClient)

    client = NotionClient("secret")
    pages, next_cursor = await client.list_pages("db-1", page_limit=10)

    assert next_cursor == ""
    assert pages[0].body_text == "Primary runbook body\nEscalate to on-call\nNested child guidance"
