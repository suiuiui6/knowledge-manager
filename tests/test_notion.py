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

        async def post(self, url, json):
            return FakeResponse()

    monkeypatch.setattr("knowledge_manager.notion.httpx.AsyncClient", FakeAsyncClient)

    client = NotionClient("secret")
    pages, next_cursor = await client.list_pages("db-1", page_limit=10)

    assert len(pages) == 1
    assert pages[0].page_id == "page-1"
    assert pages[0].title == "Runbook"
    assert next_cursor == "cursor-2"
