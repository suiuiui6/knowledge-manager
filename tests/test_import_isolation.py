from pathlib import Path

import knowledge_manager


def test_tests_import_the_repository_source_tree() -> None:
    repository_src = (Path(__file__).resolve().parents[1] / "src").resolve()
    imported_package = Path(knowledge_manager.__file__).resolve()

    assert imported_package.is_relative_to(repository_src), (
        f"tests imported {imported_package}, expected a package below {repository_src}"
    )
