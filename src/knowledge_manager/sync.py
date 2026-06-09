import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SyncConflict:
    path: str
    error: str
    action_required: str


class MarkdownSync:
    @staticmethod
    def sync_on_save(module, kb_path: Path) -> None:
        from knowledge_manager.markdown import render_markdown_module

        json_path = module.to_file_path(kb_path)
        md_path = json_path.with_suffix(".md")
        md_content = render_markdown_module(module)
        md_path.write_text(md_content, encoding="utf-8")

    @staticmethod
    def sync_on_rebuild(kb_path: Path) -> list[SyncConflict]:
        from knowledge_manager.markdown import parse_markdown_module, render_markdown_module
        from knowledge_manager.storage import list_modules, load_module

        conflicts = []
        modules = list_modules(kb_path)
        seen_paths: set[str] = set()

        for module in modules:
            json_path = module.to_file_path(kb_path)
            md_path = json_path.with_suffix(".md")
            seen_paths.add(str(json_path))

            if not md_path.exists():
                MarkdownSync.sync_on_save(module, kb_path)
                continue

            if not json_path.exists():
                continue

            try:
                json_mtime = json_path.stat().st_mtime
                md_mtime = md_path.stat().st_mtime
            except OSError:
                continue

            if abs(json_mtime - md_mtime) < 1.0:
                continue

            if json_mtime > md_mtime:
                MarkdownSync.sync_on_save(module, kb_path)
            else:
                try:
                    md_content = md_path.read_text(encoding="utf-8")
                    parsed = parse_markdown_module(md_content)
                    parsed.created_at = module.created_at
                    from knowledge_manager.storage import save_module
                    save_module(parsed, kb_path)
                except Exception as e:
                    conflicts.append(SyncConflict(
                        path=str(md_path),
                        error=str(e),
                        action_required="Manually fix Markdown format errors",
                    ))

        return conflicts

    @staticmethod
    def export_obsidian(kb_path: Path, output_dir: Path) -> int:
        from knowledge_manager.markdown import render_markdown_module
        from knowledge_manager.storage import list_modules

        output_dir.mkdir(parents=True, exist_ok=True)
        obsidian_dir = output_dir / ".obsidian"
        obsidian_dir.mkdir(exist_ok=True)

        graph_config = {
            "collapse-filter": True,
            "search": "",
            "showTags": True,
            "showAttachments": False,
            "hideUnresolved": True,
            "showOrphans": True,
            "collapse-color-groups": False,
            "colorGroups": [],
            "collapse-display": False,
            "showArrow": True,
            "textFadeMultiplier": 0,
            "nodeSizeMultiplier": 1,
            "lineSizeMultiplier": 1,
            "collapse-forces": False,
            "centerStrength": 0.5187,
            "repelStrength": 10,
            "linkStrength": 1,
            "linkDistance": 250,
            "scale": 1,
        }
        import json
        (obsidian_dir / "graph.json").write_text(json.dumps(graph_config, indent=2))

        templates_dir = obsidian_dir / "templates"
        templates_dir.mkdir(exist_ok=True)
        (templates_dir / "module.md").write_text("""---
id: ""
category: ""
title: ""
summary: ""
tags: []
confidence: medium
status: draft
source: ""
related_modules: []
created_at: ""
updated_at: ""
---

# 概述



# 细节



# 示例



# 参考



# 注意事项

""", encoding="utf-8")

        count = 0
        for module in list_modules(kb_path):
            md_text = render_markdown_module(module)
            out_path = output_dir / module.category / f"{module.id}.md"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(md_text, encoding="utf-8")
            count += 1

        _write_index_md(output_dir, kb_path)
        return count

    @staticmethod
    def enable(module, kb_path: Path) -> None:
        """Enable MD sync for future saves — update the save path to also write .md."""
        pass


def _write_index_md(output_dir: Path, kb_path: Path) -> None:
    from knowledge_manager.storage import load_index

    index = load_index(kb_path)
    if index is None:
        return

    lines = ["# Knowledge Base Index\n"]
    for cat_name, cat in index.categories.items():
        lines.append(f"## {cat_name}\n")
        lines.append(f"{cat.description}\n")
        for mod in cat.modules:
            lines.append(f"- [[{cat_name}/{mod.id}]] — {mod.summary[:100]}")
        lines.append("")

    (output_dir / "_index.md").write_text("\n".join(lines), encoding="utf-8")
