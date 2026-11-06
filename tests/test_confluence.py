from knowledge_manager.confluence import _normalize_page, _strip_html


def test_strip_html_removes_tags_and_compacts_whitespace():
    assert _strip_html("<p>Hello <strong>world</strong></p><br/>next") == "Hello world next"


def test_normalize_page_builds_url_checksum_and_heading_path():
    page = _normalize_page(
        "https://example.atlassian.net/wiki",
        {
            "id": "12345",
            "title": "JWT Runbook",
            "version": {"number": 7},
            "space": {"key": "ENG"},
            "body": {"storage": {"value": "<p>Rotate refresh tokens</p>"}},
            "_links": {"webui": "/spaces/ENG/pages/12345"},
        },
    )

    assert page.page_id == "12345"
    assert page.version == "7"
    assert page.url == "https://example.atlassian.net/wiki/spaces/ENG/pages/12345"
    assert page.heading_path == ["ENG", "JWT Runbook"]
    assert page.body_text == "Rotate refresh tokens"
    assert len(page.checksum) == 64
