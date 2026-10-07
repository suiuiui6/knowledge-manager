import importlib
import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("knowledge_manager.plugin")


@dataclass
class PluginManifest:
    name: str
    version: str
    description: str = ""
    author: str = ""
    min_km_version: str = "0.5.0"
    hooks: list[str] = field(default_factory=list)


class Plugin:
    def __init__(self, manifest: PluginManifest, module: Any, source: str):
        self.manifest = manifest
        self.module = module
        self.source = source
        self.enabled = True

    def hook(self, name: str):
        return getattr(self.module, name, None)


class PluginManager:
    def __init__(self, kb_path: Path):
        self.kb_path = kb_path
        self.plugins_dir = kb_path / ".plugins"
        self.plugins: dict[str, Plugin] = {}
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> None:
        self._ensure_dir()
        for pkg_dir in sorted(self.plugins_dir.iterdir()):
            if not pkg_dir.is_dir():
                continue
            manifest_path = pkg_dir / "plugin.json"
            if not manifest_path.exists():
                continue
            try:
                self._load_from_dir(pkg_dir)
            except Exception:
                logger.warning("Failed to load plugin from %s", pkg_dir, exc_info=True)

    def _load_from_dir(self, pkg_dir: Path) -> Optional["Plugin"]:
        manifest = PluginManifest(
            **json.loads((pkg_dir / "plugin.json").read_text(encoding="utf-8"))
        )
        spec = importlib.util.spec_from_file_location(
            f"km_plugin_{manifest.name.replace('-', '_')}", str(pkg_dir / "__init__.py")
        )
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        plugin = Plugin(manifest, mod, str(pkg_dir))
        self.plugins[manifest.name] = plugin
        logger.info("Loaded plugin: %s v%s", manifest.name, manifest.version)
        return plugin

    def install(self, package_name: str) -> bool:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", package_name],
                check=True, capture_output=True, text=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.warning("pip install failed for %s: %s", package_name, e.stderr)
            return False

    def register_local(self, plugin_dir: Path) -> Optional[Plugin]:
        self._ensure_dir()
        target = self.plugins_dir / plugin_dir.name
        if target.exists():
            logger.warning("Plugin %s already exists", plugin_dir.name)
            return None
        import shutil
        shutil.copytree(plugin_dir, target)
        return self._load_from_dir(target)

    def uninstall(self, name: str) -> bool:
        plugin = self.plugins.get(name)
        if not plugin:
            return False
        import shutil
        shutil.rmtree(Path(plugin.source), ignore_errors=True)
        del self.plugins[name]
        logger.info("Uninstalled plugin: %s", name)
        return True

    def enable(self, name: str) -> bool:
        plugin = self.plugins.get(name)
        if not plugin:
            return False
        plugin.enabled = True
        return True

    def disable(self, name: str) -> bool:
        plugin = self.plugins.get(name)
        if not plugin:
            return False
        plugin.enabled = False
        return True

    def list_plugins(self) -> list[dict]:
        return [
            {
                "name": p.manifest.name,
                "version": p.manifest.version,
                "description": p.manifest.description,
                "author": p.manifest.author,
                "enabled": p.enabled,
                "hooks": p.manifest.hooks,
            }
            for p in self.plugins.values()
        ]

    def get_enabled(self, hook_name: str) -> list[Any]:
        hooks = []
        for p in self.plugins.values():
            if not p.enabled:
                continue
            h = p.hook(hook_name)
            if h and callable(h):
                hooks.append(h)
        return hooks

    async def fire_hook(self, hook_name: str, *args, **kwargs):
        results = []
        for h in self.get_enabled(hook_name):
            try:
                result = h(*args, **kwargs)
                if hasattr(result, "__await__"):
                    result = await result
                results.append(result)
            except Exception:
                logger.warning("Hook %s in plugin %s failed", hook_name, hook_name, exc_info=True)
        return results


def search_registry(query: str, registry_url: str = "") -> list[dict]:
    import httpx
    try:
        resp = httpx.get(f"{registry_url}/search?q={query}", timeout=10)
        return resp.json().get("plugins", [])
    except Exception:
        return [
            {"name": "km-plugin-slack", "version": "0.1.0", "description": "Slack notification on review approve"},
            {"name": "km-plugin-github", "version": "0.1.0", "description": "GitHub issue integration"},
        ]
