import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from knowledge_manager.llm_clients import BaseLLMClient
from knowledge_manager.schemas import utc_now

logger = logging.getLogger("knowledge_manager.watch")

DEFAULT_INTERVALS = {"github": 300, "rss": 3600, "local": 120, "arxiv": 86400}


class WatchSource:
    def __init__(self, source_id: str, source_type: str, config: dict, category: str = ""):
        self.id = source_id
        self.type = source_type
        self.config = config
        self.category = category
        self.cursor = ""


class WatchEvent:
    def __init__(self, source_id: str, trigger_type: str = "schedule"):
        self.id = str(uuid.uuid4())
        self.source_id = source_id
        self.triggered_at = datetime.now(timezone.utc)
        self.trigger_type = trigger_type
        self.items_found = 0
        self.modules_generated = 0
        self.errors: list[str] = []
        self.took_ms = 0
        self.cursor_after = ""


class WatchScheduler:
    def __init__(self, kb_path: Path, llm_client: Optional[BaseLLMClient] = None):
        self.kb_path = kb_path
        self.llm = llm_client
        self.sources: dict[str, WatchSource] = {}
        self.events: list[WatchEvent] = []
        self._running = False

    def add_source(self, source_type: str, config: dict, category: str = "") -> WatchSource:
        sid = f"{source_type}-{len(self.sources)}"
        source = WatchSource(sid, source_type, config, category)
        self.sources[sid] = source
        self._save_config()
        return source

    def remove_source(self, source_id: str) -> bool:
        if source_id in self.sources:
            del self.sources[source_id]
            self._save_config()
            return True
        return False

    async def poll_source(self, source_id: str) -> WatchEvent:
        import time
        t0 = time.time()

        source = self.sources.get(source_id)
        if not source:
            event = WatchEvent(source_id)
            event.errors.append("Source not found")
            return event

        event = WatchEvent(source_id, "schedule")
        try:
            if source.type == "local":
                result = await self._poll_local(source)
            elif source.type == "doc_dir":
                result = await self._poll_doc_dir(source)
            else:
                event.items_found = 0
                event.took_ms = int((time.time() - t0) * 1000)
                return event

            event.items_found = result.get("items_found", 0)
            event.modules_generated = result.get("modules_generated", 0)
            event.cursor_after = result.get("cursor", "")
        except Exception as e:
            event.errors.append(str(e))
            logger.warning("Poll failed for %s: %s", source_id, e)

        event.took_ms = int((time.time() - t0) * 1000)
        self.events.append(event)
        return event

    async def _poll_local(self, source: WatchSource) -> dict:
        watch_path = Path(source.config.get("path", ""))
        if not watch_path.exists():
            return {"items_found": 0, "modules_generated": 0}

        patterns = source.config.get("patterns", ["*.md", "*.txt"])
        items_found = 0
        for pat in patterns:
            for f in watch_path.rglob(pat):
                if f.stat().st_mtime > (datetime.now().timestamp() - 3600):
                    items_found += 1

        return {"items_found": items_found, "modules_generated": 0, "cursor": str(datetime.now().timestamp())}

    async def _poll_doc_dir(self, source: WatchSource) -> dict:
        watch_path = Path(source.config.get("path", ""))
        if not watch_path.exists():
            return {"items_found": 0, "modules_generated": 0}

        count = len(list(watch_path.rglob("*.md")))
        return {"items_found": count, "modules_generated": 0, "cursor": str(datetime.now().timestamp())}

    async def poll_all(self) -> list[WatchEvent]:
        events = []
        for sid in list(self.sources.keys()):
            events.append(await self.poll_source(sid))
        return events

    def get_status(self) -> dict:
        return {
            "sources": len(self.sources),
            "events_logged": len(self.events),
            "sources_detail": {
                sid: {"type": s.type, "cursor": s.cursor[:20]}
                for sid, s in self.sources.items()
            },
        }

    def _save_config(self) -> None:
        watch_dir = self.kb_path / ".watch"
        watch_dir.mkdir(exist_ok=True)
        sources_data = [
            {"id": s.id, "type": s.type, "config": s.config, "category": s.category}
            for s in self.sources.values()
        ]
        (watch_dir / "sources.json").write_text(json.dumps(sources_data, indent=2))

    def load_config(self) -> None:
        config_path = self.kb_path / ".watch" / "sources.json"
        if not config_path.exists():
            return
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            for item in data:
                ws = WatchSource(item["id"], item["type"], item["config"], item.get("category", ""))
                self.sources[ws.id] = ws
        except Exception:
            pass
