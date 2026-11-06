import re
from dataclasses import dataclass, field
from pathlib import Path

WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+?)(?:#([^\]|]+?))?(?:\|([^\]]+?))?\]\]")
TRANSCLUDE_PATTERN = re.compile(r"!\[\[([^\]|#]+?)(?:#([^\]|]+?))?(?:\|([^\]]+?))?\]\]")


@dataclass
class Wikilink:
    target: str
    section: str = ""
    display_text: str = ""
    resolved: bool = False
    resolved_path: str = ""
    is_transclude: bool = False


@dataclass
class BlockReference:
    """A resolved reference to a specific section/paragraph within a module."""
    module_key: str
    module_title: str
    section_name: str = ""
    section_text: str = ""
    resolved: bool = False


def parse_wikilinks(text: str) -> list[Wikilink]:
    links = []
    seen = set()
    for match in WIKILINK_PATTERN.finditer(text):
        target = match.group(1).strip()
        section = match.group(2).strip() if match.group(2) else ""
        display = match.group(3).strip() if match.group(3) else ""
        uid = f"{target}#{section}"
        if uid not in seen:
            links.append(Wikilink(target=target, section=section, display_text=display))
            seen.add(uid)
    return links


def parse_transclusions(text: str) -> list[Wikilink]:
    """Parse ![[...]] transclusion syntax for embedded content."""
    links = []
    seen = set()
    for match in TRANSCLUDE_PATTERN.finditer(text):
        target = match.group(1).strip()
        section = match.group(2).strip() if match.group(2) else ""
        display = match.group(3).strip() if match.group(3) else ""
        uid = f"!{target}#{section}"
        if uid not in seen:
            links.append(Wikilink(target=target, section=section, display_text=display, is_transclude=True))
            seen.add(uid)
    return links


def resolve_wikilinks(links: list[Wikilink], kb_path: Path) -> list[Wikilink]:
    from knowledge_manager.storage import load_index, load_module

    index = load_index(kb_path)
    if index is None:
        return links

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


def resolve_block_reference(wikilink: Wikilink, kb_path: Path) -> BlockReference | None:
    """Resolve a wikilink to a specific section within a module."""
    if not wikilink.resolved or not wikilink.resolved_path:
        return None

    from knowledge_manager.storage import load_module

    parts = wikilink.resolved_path.split("/", 1)
    if len(parts) != 2:
        return None

    module = load_module(parts[1], parts[0], kb_path)
    if module is None:
        return None

    ref = BlockReference(
        module_key=wikilink.resolved_path,
        module_title=module.title,
        section_name=wikilink.section,
        resolved=True,
    )

    if not wikilink.section:
        return ref

    # Search for section heading in content
    full_text = f"{module.content.overview}\n{module.content.details}\n{module.content.examples}\n{module.content.caveats}"
    section_lower = wikilink.section.lower().replace("-", " ")

    # Try to find heading matching section name
    heading_pattern = re.compile(rf"^#{{{1,3}}}\s*(.*?{re.escape(section_lower)}.*?)$", re.IGNORECASE | re.MULTILINE)
    match = heading_pattern.search(full_text)
    if match:
        # Extract content under this heading until next heading
        start = match.end()
        next_heading = re.search(r"^#{1,3}\s", full_text[start:], re.MULTILINE)
        end = start + next_heading.start() if next_heading else min(start + 500, len(full_text))
        ref.section_text = full_text[start:end].strip()[:500]
    else:
        # Fallback: search for the section name anywhere in text
        idx = full_text.lower().find(section_lower)
        if idx >= 0:
            ref.section_text = full_text[max(0, idx - 20):idx + 400].strip()

    return ref


def extract_transclusions(text: str, kb_path: Path) -> str:
    """Process transclusions in text: ![[module#section]] → embedded content."""
    links = parse_transclusions(text)
    resolved = resolve_wikilinks(links, kb_path)

    result = text
    for link in resolved:
        if not link.resolved:
            continue
        ref = resolve_block_reference(link, kb_path)
        if ref and ref.resolved:
            embed = f"> **📌 {ref.module_title}**"
            if ref.section_name:
                embed += f" — *{ref.section_name}*"
            embed += f"\n> \n> {ref.section_text}"
            old = f"![[{link.target}"
            if link.section:
                old += f"#{link.section}"
            old += "]]"
            result = result.replace(old, embed)

    return result


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
