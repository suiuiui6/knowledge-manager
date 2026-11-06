import pytest
from pathlib import Path

from knowledge_manager.linter import DeepLinter, PAIR_FILTERS, _title_keyword_overlap
from knowledge_manager.schemas import (
    Contradiction,
    ContradictionEvidence,
    ContradictionType,
    Module,
    ModuleContent,
    ModuleMetadata,
    Severity,
)


class TestTitleOverlap:
    def test_overlap(self):
        a = Module(id="a", category="x", title="JWT Token Configuration", summary="test summary text here ok",
                   content=ModuleContent(overview="overview text for testing", details="a details with enough chars for validation"),
                   metadata=ModuleMetadata(tags=["jwt"]))
        b = Module(id="b", category="x", title="JWT Token Rotation", summary="test summary text here ok",
                   content=ModuleContent(overview="overview text for testing", details="b details with enough chars for validation"),
                   metadata=ModuleMetadata(tags=["jwt"]))
        assert _title_keyword_overlap(a, b) > 0.5

    def test_no_overlap(self):
        a = Module(id="a", category="x", title="JWT Config", summary="test summary text here ok",
                   content=ModuleContent(overview="overview text for testing", details="a details with enough chars for validation"),
                   metadata=ModuleMetadata(tags=["jwt"]))
        b = Module(id="b", category="x", title="Database Pooling", summary="test summary text here ok",
                   content=ModuleContent(overview="overview text for testing", details="b details with enough chars for validation"),
                   metadata=ModuleMetadata(tags=["db"]))
        assert _title_keyword_overlap(a, b) == 0.0


class TestPairFilters:
    @pytest.fixture
    def mod_a(self):
        return Module(id="a", category="auth", title="JWT Config", summary="test summary text here",
                      content=ModuleContent(overview="overview for mod a test", details="details for mod a with enough chars for validation"),
                      metadata=ModuleMetadata(tags=["jwt", "auth"], related_modules=["auth/b"]))

    @pytest.fixture
    def mod_b(self):
        return Module(id="b", category="auth", title="OAuth Flow", summary="test summary text here",
                      content=ModuleContent(overview="overview for mod b test", details="details for mod b with enough chars for validation"),
                      metadata=ModuleMetadata(tags=["oauth", "auth"], related_modules=["auth/a"]))

    @pytest.fixture
    def mod_c(self):
        return Module(id="c", category="deploy", title="K8s Config", summary="test summary text here",
                      content=ModuleContent(overview="overview for mod c test", details="details for mod c with enough chars for validation"),
                      metadata=ModuleMetadata(tags=["k8s", "deploy"]))

    def test_same_category(self, mod_a, mod_b):
        assert PAIR_FILTERS["same_category"](mod_a, mod_b) is True

    def test_different_category(self, mod_a, mod_c):
        assert PAIR_FILTERS["same_category"](mod_a, mod_c) is False

    def test_shared_tags(self, mod_a, mod_b):
        assert PAIR_FILTERS["shared_tags"](mod_a, mod_b) is True

    def test_no_shared_tags(self, mod_a, mod_c):
        assert PAIR_FILTERS["shared_tags"](mod_a, mod_c) is False

    def test_mutual_reference(self, mod_a, mod_b):
        assert PAIR_FILTERS["mutual_reference"](mod_a, mod_b) is True

    def test_no_mutual_reference(self, mod_a, mod_c):
        assert PAIR_FILTERS["mutual_reference"](mod_a, mod_c) is False


class TestDeepLinter:
    @pytest.fixture
    def kb_with_modules(self, tmp_path):
        kb = tmp_path / "test_kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index, save_module, rebuild_index

        save_index(Index(description="Test KB"), kb)

        mod_a = Module(
            id="jwt", category="auth", title="JWT Configuration",
            summary="JWT token settings for authentication",
            content=ModuleContent(overview="JWT overview", details="JWT details with enough chars for validation"),
            metadata=ModuleMetadata(tags=["jwt", "auth"], confidence="high",
                                    related_modules=["auth/old-session"]),
        )
        mod_b = Module(
            id="old-session", category="auth", title="Old Session Management",
            summary="Legacy session management approach",
            content=ModuleContent(overview="old session overview", details="old session details with enough chars here"),
            metadata=ModuleMetadata(tags=["session"], confidence="low", status="deprecated"),
        )
        save_module(mod_a, kb)
        save_module(mod_b, kb)
        rebuild_index(kb)
        return kb

    def test_structural_check_stale_ref(self, kb_with_modules):
        linter = DeepLinter(kb_with_modules)
        issues = linter.lint_all("quick")
        stale = [i for i in issues if i.type == ContradictionType.STALE_REFERENCE]
        assert len(stale) >= 1
        assert "auth/old-session" in str(stale[0].modules)

    def test_structural_check_auto_fixable(self, kb_with_modules):
        linter = DeepLinter(kb_with_modules)
        issues = linter.lint_all("quick")
        stale_refs = [i for i in issues if i.type == ContradictionType.STALE_REFERENCE]
        for i in stale_refs:
            if "deprecated" in i.description:
                assert i.auto_fixable is True

    def test_generate_candidates(self, kb_with_modules):
        from knowledge_manager.storage import list_modules
        linter = DeepLinter(kb_with_modules)
        modules = list_modules(kb_with_modules)
        candidates = linter._generate_candidates(modules)
        assert len(candidates) > 0

    def test_lint_quick_returns_list(self, kb_with_modules):
        linter = DeepLinter(kb_with_modules)
        issues = linter.lint_all("quick")
        assert isinstance(issues, list)


class TestContradictionSchema:
    def test_contradiction_creation(self):
        c = Contradiction(
            id="test-1",
            type=ContradictionType.FACT,
            severity=Severity.ERROR,
            modules=["auth/jwt", "auth/oauth"],
            description="Test contradiction",
        )
        assert c.type == ContradictionType.FACT
        assert c.severity == Severity.ERROR
        assert len(c.modules) == 2

    def test_contradiction_types(self):
        for t in ContradictionType:
            assert t.value in ("fact", "decision", "timeline", "terminology", "stale_ref")

    def test_severity_levels(self):
        for s in Severity:
            assert s.value in ("error", "warning", "info")
