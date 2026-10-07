import asyncio
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("knowledge_manager.vector")


class VectorIndex:
    def __init__(self, kb_path: Path, provider: str = "ollama", model: str = "bge-m3",
                 dimensions: int = 1024, ollama_base_url: str = "http://localhost:11434"):
        self.kb_path = kb_path
        self.provider = provider
        self.model = model
        self.dimensions = dimensions
        self.ollama_base_url = ollama_base_url
        self.embeddings: Optional["np.ndarray"] = None
        self.module_keys: list[str] = []
        self._lock = threading.Lock()
        self._cache_path = kb_path / ".cache" / "vector_index.npz"

    async def rebuild(self, on_progress=None) -> None:
        try:
            import numpy as np
        except ImportError:
            logger.warning("numpy not installed, vector search disabled")
            return

        from knowledge_manager.storage import load_index, load_module

        index = load_index(self.kb_path)
        if index is None:
            return

        modules = []
        for cat in index.categories.values():
            for mod_summary in cat.modules:
                module = load_module(mod_summary.id, mod_summary.category, self.kb_path)
                if module and module.metadata.status in ("published", "reviewed"):
                    modules.append(module)

        if not modules:
            return

        texts = []
        keys = []
        for i, module in enumerate(modules):
            text = f"{module.title}\n{module.summary}\n{' '.join(module.metadata.tags)}\n{module.content.overview}\n{module.content.details}"
            texts.append(text)
            keys.append(f"{module.category}/{module.id}")
            if on_progress and i % 10 == 0:
                on_progress(i, len(modules))

        try:
            embeddings = await self._embed(texts)
        except Exception as e:
            logger.warning("Embedding failed: %s", e)
            return

        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

        with self._lock:
            self.embeddings = embeddings
            self.module_keys = keys

        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self._cache_path, embeddings=embeddings, module_keys=np.array(keys, dtype=object))

    def search(self, query: str, top_k: int = 20) -> list[tuple[str, float]]:
        try:
            import numpy as np
        except ImportError:
            return []

        if self.embeddings is None:
            try:
                self._load_from_cache()
            except Exception:
                return []

        if self.embeddings is None or len(self.embeddings) == 0:
            return []

        try:
            query_embedding = asyncio.run(self._embed([query]))
            query_embedding = query_embedding[0] / np.linalg.norm(query_embedding[0])
        except Exception:
            return []

        with self._lock:
            scores = np.dot(self.embeddings, query_embedding)
            if top_k >= len(scores):
                indices = np.argsort(-scores)
            else:
                indices = np.argpartition(-scores, top_k)[:top_k]
                indices = indices[np.argsort(-scores[indices])]

            return [(self.module_keys[i], float(scores[i])) for i in indices[:top_k]]

    async def _embed(self, texts: list[str]) -> "np.ndarray":
        import numpy as np

        if self.provider == "ollama":
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ollama_base_url}/api/embed",
                    json={"model": self.model, "input": texts},
                    timeout=60,
                )
                data = response.json()
                return np.array(data["embeddings"], dtype=np.float32)

        raise ValueError(f"Unknown embedding provider: {self.provider}")

    def _load_from_cache(self) -> None:
        if not self._cache_path.exists():
            return
        import numpy as np
        data = np.load(self._cache_path, allow_pickle=True)
        with self._lock:
            self.embeddings = data["embeddings"]
            self.module_keys = list(data["module_keys"])
