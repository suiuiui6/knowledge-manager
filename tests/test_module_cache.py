from knowledge_manager.schemas import Index, Module, ModuleContent
from knowledge_manager.storage import list_modules, save_index, save_module


def test_list_modules_reuses_cached_module_set_until_storage_changes(tmp_path):
    from knowledge_manager.module_cache import ModuleCache

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="cache test"), kb)

    module = Module(
        id="mod-1",
        category="ops",
        title="Ops Module",
        summary="Ops module summary.",
        content=ModuleContent(
            overview="Ops overview text.",
            details="Ops details long enough for validation.",
        ),
    )
    save_module(module, kb)

    cache = ModuleCache()
    assert cache.get(kb, (1, 1)) is None

    first = list_modules(kb)
    second = list_modules(kb)

    assert [m.id for m in first] == [m.id for m in second] == ["mod-1"]
