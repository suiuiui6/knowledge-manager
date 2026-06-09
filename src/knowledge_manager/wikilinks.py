import re
from dataclasses import dataclass
from pathlib import Path

WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]")


@dataclass
class Wikilink:
    target: str
    display_text: str = ""
    resolved: bool = False
    resolved_path: str = ""


def parse_wikilinks(text: str) -> list[Wikilink]:
    links = []
    seen = set()
    for match in WIKILINK_PATTERN.finditer(text):
        target = match.group(1).strip()
        display = match.group(2).strip() if match.group(2) else ""
        if target not in seen:
            links.append(Wikilink(target=target, display_text=display))
            seen.add(target)
    return links


def resolve_wikilinks(links: list[Wikilink], kb_path: Path) -> list[Wikilink]:
    from knowledge_manager.storage import load_index, load_module

    index = load_index(kb_path)
    if index is None:
        return links

    # Build lookup: id -> (category, title), title_lower -> key
    id_map: dict[str, str] = {}
    title_map: dict[str, str] = {}
    for cat_name, cat in index.categories.items():
        for mod in cat.modules:
            key = f"{cat_name}/{mod.id}"
            id_map[mod.id] = key
            title_map[mod.title.lower()] = key

    for link in links:
        # Strategy 1: exact path "category/id"
        if "/" in link.target:
            parts = link.target.split("/", 1)
            if parts[0] in index.categories:
                for mod in index.categories[parts[0]].modules:
                    if mod.id == parts[1]:
                        link.resolved = True
                        link.resolved_path = link.target
                        break
            if link.resolved:
                continue

        # Strategy 2: ID search
        if link.target in id_map:
            link.resolved = True
            link.resolved_path = id_map[link.target]
            continue

        # Strategy 3: title search
        target_lower = link.target.lower()
        if target_lower in title_map:
            link.resolved = True
            link.resolved_path = title_map[target_lower]
            continue

        # Strategy 4: fuzzy content search
        for cat_name, cat in index.categories.items():
            for mod in cat.modules:
                if link.target.lower() in mod.summary.lower():
                    link.resolved = True
                    link.resolved_path = f"{cat_name}/{mod.id}"
                    break
            if link.resolved:
                break

    return links


def auto_update_related_modules(module, kb_path: Path) -> list[str]:
    full_text = " ".join([
        module.content.overview, module.content.details,
        module.content.examples, module.content.references, module.content.caveats,
    ])
    links = parse_wikilinks(full_text)
    resolved = resolve_wikilinks(links, kb_path)
    new_related = set(module.metadata.related_modules)
    for link in resolved:
        if link.resolved and link.resolved_path != f"{module.category}/{module.id}":
            new_related.add(link.resolved_path)
    return sorted(new_related)
