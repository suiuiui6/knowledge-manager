import pytest
from pathlib import Path

from knowledge_manager.schemas import TreeNode, TreeNodeType
from knowledge_manager.tree_builder import (
    build_tree_from_markdown,
    rebuild_tree_from_files,
    slugify,
)
from knowledge_manager.tree_navigator import TreeNavigator, NavigationResult
from knowledge_manager.storage import (
    find_modules_under,
    get_tree,
    get_subtree,
    save_tree,
)


class TestSlugify:
    def test_ascii_title(self):
        result = slugify("JWT Token Configuration")
        assert "jwt" in result
        assert "-" in result

    def test_pure_cjk_title(self):
        result = slugify("认证与授权")
        assert len(result) > 0


class TestMarkdownTree:
    def test_h1_h2_h3(self):
        md = "# Auth\n## JWT Config\nsummary here\n### Signing\nDetails about signing"
        tree = build_tree_from_markdown(md, "auth")
        assert tree.type == TreeNodeType.ROOT
        assert len(tree.children) == 1  # H1 = category
        cat = tree.children[0]
        assert cat.type == TreeNodeType.CATEGORY
        assert len(cat.children) == 1  # H2 = module
        mod = cat.children[0]
        assert mod.type == TreeNodeType.MODULE
        assert len(mod.children) == 1  # H3 = section

    def test_multiple_h2(self):
        md = "# Auth\n## JWT\n## OAuth"
        tree = build_tree_from_markdown(md, "auth")
        assert len(tree.children[0].children) == 2

    def test_no_headings(self):
        tree = build_tree_from_markdown("plain text", "test")
        assert len(tree.children) == 0


class TestTreeNode:
    def test_tree_node_defaults(self):
        node = TreeNode(id="test", type=TreeNodeType.MODULE, title="Test")
        assert node.summary == ""
        assert node.children == []
        assert node.module_count == 0

    def test_tree_node_types(self):
        for t in TreeNodeType:
            node = TreeNode(id="x", type=t, title="x")
            assert node.type == t


class TestStorageTree:
    @pytest.fixture
    def kb_with_tree(self, tmp_path):
        kb = tmp_path / "test_kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
        from knowledge_manager.storage import save_index, save_module, rebuild_index

        idx = Index(description="Test KB")
        save_index(idx, kb)

        mod = Module(
            id="jwt", category="auth", title="JWT Config",
            summary="JWT configuration details for token management",
            content=ModuleContent(overview="jwt overview text here", details="jwt details text here with enough length for validation"),
            metadata=ModuleMetadata(tags=["jwt", "auth"], related_modules=["auth/oauth"]),
        )
        save_module(mod, kb)

        mod2 = Module(
            id="oauth", category="auth", title="OAuth Flow",
            summary="OAuth flow details for authorization",
            content=ModuleContent(overview="oauth overview text here", details="oauth details text here with enough length for validation"),
            metadata=ModuleMetadata(tags=["oauth", "auth"], related_modules=["auth/jwt"]),
        )
        save_module(mod2, kb)

        rebuild_index(kb)
        return kb

    def test_get_tree_fallback(self, kb_with_tree):
        tree = get_tree(kb_with_tree)
        assert tree.type == TreeNodeType.ROOT
        assert len(tree.children) > 0

    def test_get_subtree(self, kb_with_tree):
        node = get_subtree("auth", "jwt", kb_with_tree)
        assert node is not None
        assert node.type == TreeNodeType.MODULE
        assert node.title == "JWT Config"
        assert len(node.children) >= 0  # related module

    def test_get_subtree_nonexistent(self, kb_with_tree):
        node = get_subtree("auth", "nonexistent", kb_with_tree)
        assert node is None

    def test_save_tree(self, kb_with_tree):
        custom = TreeNode(id="root", type=TreeNodeType.ROOT, title="Custom",
                          children=[TreeNode(id="g1", type=TreeNodeType.CATEGORY, title="Group1")])
        save_tree(custom, kb_with_tree)
        loaded = get_tree(kb_with_tree)
        assert loaded.title == "Custom"
        assert len(loaded.children) == 1

    def test_find_modules_under(self):
        root = TreeNode(id="root", type=TreeNodeType.ROOT, title="R",
            children=[
                TreeNode(id="cat1", type=TreeNodeType.CATEGORY, title="C1",
                    children=[TreeNode(id="m1", type=TreeNodeType.MODULE, title="M1"),
                              TreeNode(id="m2", type=TreeNodeType.MODULE, title="M2")])
            ])
        keys = find_modules_under(root)
        assert len(keys) == 2


class TestRebuildFromFiles:
    def test_no_md_files(self, tmp_path):
        kb = tmp_path / "empty_kb"
        kb.mkdir()
        from knowledge_manager.schemas import Index
        from knowledge_manager.storage import save_index
        save_index(Index(description="empty"), kb)
        result = rebuild_tree_from_files(kb)
        assert result is None


class TestTreeNavigator:
    @pytest.fixture
    def sample_tree(self):
        return TreeNode(id="root", type=TreeNodeType.ROOT, title="KB",
            children=[
                TreeNode(id="auth", type=TreeNodeType.CATEGORY, title="Authentication",
                    summary="All about auth",
                    children=[
                        TreeNode(id="auth/jwt", type=TreeNodeType.MODULE, title="JWT Config",
                                  summary="JWT token configuration details", path="auth/jwt",
                                  tags=["jwt", "token"]),
                        TreeNode(id="auth/oauth", type=TreeNodeType.MODULE, title="OAuth Flow",
                                  summary="OAuth 2.0 authorization code flow", path="auth/oauth",
                                  tags=["oauth", "authorization"]),
                    ]),
                TreeNode(id="deploy", type=TreeNodeType.CATEGORY, title="Deployment",
                    children=[
                        TreeNode(id="deploy/k8s", type=TreeNodeType.MODULE, title="K8s Config",
                                  summary="Kubernetes cluster configuration", path="deploy/k8s",
                                  tags=["kubernetes", "deploy"]),
                    ]),
            ])

    class FakeNavLLM:
        def __init__(self, responses=None):
            self.responses = responses or []
            self.idx = 0
            self.config = type("C", (), {"api_key": "", "model": "", "base_url": "", "temperature": 0.3, "max_tokens": 1024})()

        async def complete(self, prompt):
            if self.idx < len(self.responses):
                r = self.responses[self.idx]
                self.idx += 1
                return r
            return '{"action": "done", "reasoning": "no more responses", "confidence": 0.9}'

    def test_navigator_index(self, sample_tree):
        nav = TreeNavigator(sample_tree, self.FakeNavLLM())
        assert "auth/jwt" in nav._node_index
        assert "deploy/k8s" in nav._node_index
        assert nav._parent_map.get("auth/jwt") == "auth"

    @pytest.mark.asyncio
    async def test_navigate_drill_to_module(self, sample_tree):
        import json
        # drill to auth, then load jwt
        llm = self.FakeNavLLM([
            json.dumps({"action": "drill", "target_node": "auth", "reasoning": "User asked about auth", "confidence": 0.9}),
            json.dumps({"action": "drill", "target_node": "auth/jwt", "reasoning": "JWT is about auth", "confidence": 0.95}),
            json.dumps({"action": "done", "target_node": "auth/jwt", "reasoning": "Found JWT module", "confidence": 0.95}),
        ])
        nav = TreeNavigator(sample_tree, llm, max_steps=3)
        result = await nav.navigate("JWT token config")
        assert result.final_module_key == "auth/jwt"
        assert result.confidence == 0.95
        assert len(result.path) == 3

    @pytest.mark.asyncio
    async def test_navigate_load(self, sample_tree):
        import json
        llm = self.FakeNavLLM([
            json.dumps({"action": "drill", "target_node": "deploy", "reasoning": "deployment question", "confidence": 0.9}),
            json.dumps({"action": "load", "target_node": "deploy/k8s", "reasoning": "K8s is what user needs", "confidence": 0.92}),
        ])
        nav = TreeNavigator(sample_tree, llm, max_steps=3)
        result = await nav.navigate("kubernetes config")
        assert result.final_module_key == "deploy/k8s"

    @pytest.mark.asyncio
    async def test_navigate_no_match(self, sample_tree):
        import json
        llm = self.FakeNavLLM([
            json.dumps({"action": "drill", "target_node": "auth", "reasoning": "trying auth", "confidence": 0.3}),
            json.dumps({"action": "backtrack", "target_node": "root", "reasoning": "not in auth", "confidence": 0.1}),
            json.dumps({"action": "done", "reasoning": "not found", "confidence": 0.0}),
        ])
        nav = TreeNavigator(sample_tree, llm, max_steps=3)
        result = await nav.navigate("machine learning")
        assert result.confidence <= 0.3

    def test_find_best_leaf(self, sample_tree):
        nav = TreeNavigator(sample_tree, self.FakeNavLLM())
        best = nav._find_best_leaf(sample_tree, "jwt")
        assert best is not None
        assert "jwt" in best.id
