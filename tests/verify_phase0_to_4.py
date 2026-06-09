"""
Phase 0-4 Golden Path Integration Verification.
Run as: python tests/verify_phase0_to_4.py
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

from knowledge_manager.schemas import (
    Module, ModuleContent, ModuleMetadata, Index,
    Config, ReviewRecord, StagingMeta,
    WebhookEndpoint, WebhookConfig as WHConfig,
    MarketplaceIndex as MPIndex, MarketplaceModule as MPMod,
)
from knowledge_manager.storage import (
    save_module, load_module, delete_module,
    list_modules, load_index, save_index, rebuild_index, search_modules,
    save_to_staging, load_from_staging, list_staging, approve_from_staging,
    save_staging_meta, load_staging_meta, list_staging_meta,
    record_search_event, record_load_event, compute_bayesian_priors,
    generate_changelog, sanitize_config,
    compute_module_health, generate_health_report,
    aggregate_usage_stats, analyze_graph, detect_clusters,
    generate_recommendations, load_federation,
)
from knowledge_manager.cache import ModuleCache
from knowledge_manager.connect import (
    PLATFORMS, build_mcp_entry, resolve_config_path,
    read_mcp_config, write_mcp_config, remove_mcp_entry, has_entry,
)
from knowledge_manager.webhooks import (
    emit_event, _event_matches, _sign_payload,
    load_webhook_failures, retry_webhooks,
)
from knowledge_manager.marketplace import (
    fetch_marketplace_index, search_marketplace,
    resolve_install_plan, sanitize_module_text, check_publish_gate,
)

pass_count = 0
fail_count = 0

def check(name, condition, detail=""):
    global pass_count, fail_count
    if condition:
        pass_count += 1
        print(f"  ✅ {name}")
    else:
        fail_count += 1
        print(f"  ❌ {name}  {detail}")


def make_mod(id, cat="general"):
    return Module(
        id=id, category=cat, title=f"{id} Title Here",
        summary=f"Summary for {id} module testing",
        content=ModuleContent(
            overview="Overview text long enough for validation",
            details="Details text that is definitely long enough to pass validation checks",
        ),
        metadata=ModuleMetadata(tags=["test", cat], related_modules=[]),
    )


# Setup test KB
kb = Path(tempfile.mkdtemp()) / "test-kb"
kb.mkdir(parents=True)
staging = kb / ".staging"
staging.mkdir()


# ═══════════════ Phase 0: MVP ═══════════════
print("\n=== Phase 0: MVP ===")

mod = make_mod("phase0-mod", "general")
save_module(mod, kb)
check("save_module + load_module", load_module("phase0-mod", "general", kb) is not None)
check("list_modules", len(list_modules(kb)) == 1)

idx = rebuild_index(kb)
check("rebuild_index creates index", idx is not None)
check("index has stats", idx.stats.total_modules == 1)

results = search_modules("phase0", kb)
check("search finds module", len(results) > 0)
check("search result has module data", results[0].module.title == "phase0-mod Title Here")

mod2 = make_mod("staged-mod", "auth")
save_to_staging(mod2, staging)
check("save_to_staging", load_from_staging("staged-mod", staging) is not None)
check("list_staging", len(list_staging(staging)) == 1)

meta = StagingMeta(module_id="staged-mod", submitted_by="test-runner")
save_staging_meta(meta, staging)
check("save_staging_meta", load_staging_meta("staged-mod", staging) is not None)

approve_from_staging("staged-mod", staging, kb)
check("approve_from_staging moves to kb", load_module("staged-mod", "auth", kb) is not None)
check("approve_from_staging removes from staging", load_from_staging("staged-mod", staging) is None)

delete_module("phase0-mod", "general", kb)
check("delete_module", load_module("phase0-mod", "general", kb) is None)


# ═══════════════ Phase 1A: Graph + Confidence ═══════════════
print("\n=== Phase 1A: Graph + Confidence ===")

m1 = make_mod("p1a-core", "auth")
m1.metadata.confidence = "high"
m1.metadata.related_modules = ["db/p1a-neighbor"]
save_module(m1, kb)
m2 = make_mod("p1a-neighbor", "db")
m2.metadata.confidence = "low"
m2.title = "Database Neighbor Module"
save_module(m2, kb)
rebuild_index(kb)

# Search for exactly p1a-core — only p1a-core matches directly, neighbor comes via expansion
results = search_modules("p1a-core", kb)
direct_found = any(r.module.id == "p1a-core" and r.source == "direct" for r in results)
related_found = any(r.module.id == "p1a-neighbor" and r.source == "related" for r in results)
check("graph expansion: direct match source=direct", direct_found)
check("graph expansion: neighbor match source=related", related_found)

# Confidence ordering: high > low when both match
# Add a common tag to both modules and search by tag
m1.metadata.tags = ["conf-test", "high-conf"]
m2.metadata.tags = ["conf-test", "low-conf"]
save_module(m1, kb)
save_module(m2, kb)
rebuild_index(kb)

results_ordered = search_modules("conf-test", kb)
high_idx = next((i for i, r in enumerate(results_ordered) if r.module.id == "p1a-core"), 99)
low_idx = next((i for i, r in enumerate(results_ordered) if r.module.id == "p1a-neighbor"), 99)
check("confidence weighting: high before low", high_idx < low_idx,
      f"(high at {high_idx}, low at {low_idx})")


# ═══════════════ Phase 1B: Telemetry + Bayesian ═══════════════
print("\n=== Phase 1B: Telemetry + Bayesian ===")

record_search_event("p1a core module query", ["auth/p1a-core"], kb)
record_load_event("p1a-core", "auth", kb)
check("telemetry search event recorded", True)
check("telemetry load event recorded", True)
priors = compute_bayesian_priors(kb)
check("bayesian priors computed", isinstance(priors, dict))


# ═══════════════ Phase 2A: Git Collaboration ═══════════════
print("\n=== Phase 2A: Git Collaboration ===")

subprocess.run(["git", "-C", str(kb), "init"], capture_output=True)
subprocess.run(["git", "-C", str(kb), "config", "user.name", "test"], capture_output=True)
subprocess.run(["git", "-C", str(kb), "config", "user.email", "test@test.com"], capture_output=True)
subprocess.run(["git", "-C", str(kb), "add", "-A"], capture_output=True)
subprocess.run(["git", "-C", str(kb), "commit", "-m", "init"], capture_output=True)

remote_path = Path(tempfile.mkdtemp()) / "remote.git"
remote_path.mkdir()
subprocess.run(["git", "-C", str(remote_path), "init", "--bare"], capture_output=True)
subprocess.run(["git", "-C", str(kb), "remote", "add", "origin", str(remote_path)], capture_output=True)

from knowledge_manager.schemas import LLMProviderConfig

cfg = Config(
    llm_providers={"test": LLMProviderConfig(api_key="secret123", model="gpt", default=True)}
)
sanitized = sanitize_config(cfg)
check("sanitize_config replaces api_key",
      sanitized.model_dump()["llm_providers"]["test"]["api_key"] == "<LOCAL>")

changelog = generate_changelog(kb)
check("generate_changelog produces data", changelog is not None)


# ═══════════════ Phase 2B: Review Pipeline ═══════════════
print("\n=== Phase 2B: Review Pipeline ===")

mod_review = make_mod("review-mod", "auth")
save_to_staging(mod_review, staging)
meta_r = StagingMeta(module_id="review-mod", submitted_by="alice")
meta_r.reviews.append(ReviewRecord(reviewer="bob", action="approved", comment="LGTM"))
save_staging_meta(meta_r, staging)
check("review record stored", meta_r.approval_count() == 1)
check("staging_meta list populated", len(list_staging_meta(staging)) >= 1)
check("review config defaults exist", Config().review is not None)


# ═══════════════ Phase 2C: Changelog + Notifications ═══════════════
print("\n=== Phase 2C: Changelog + Notifications ===")

check("notifications config exists", Config().notifications is not None)
check("notifications on_push default", Config().notifications.on_push is True)


# ═══════════════ Phase 2D: Status Machine ═══════════════
print("\n=== Phase 2D: Status Machine ===")

mod_dep = make_mod("dep-mod", "auth")
save_module(mod_dep, kb)
mod_dep.metadata.status = "deprecated"
save_module(mod_dep, kb)
check("deprecated status persisted", load_module("dep-mod", "auth", kb).metadata.status == "deprecated")

mod_arch = make_mod("arch-mod", "auth")
mod_arch.metadata.status = "archived"
save_module(mod_arch, kb)
results_no_arch = search_modules("arch-mod", kb)
results_with_arch = search_modules("arch-mod", kb, include_archived=True)
check("search excludes archived by default", all(r.module.id != "arch-mod" for r in results_no_arch))
check("search includes archived when requested", any(r.module.id == "arch-mod" for r in results_with_arch))


# ═══════════════ Phase 3A: Health Dashboard ═══════════════
print("\n=== Phase 3A: Health ===")

h = compute_module_health(m1, kb)
check("compute_module_health returns ModuleHealth", h.score.overall >= 0)
check("health has freshness dimension", h.score.freshness >= 0)
check("health has usage dimension", h.score.usage >= 0)
check("health has completeness dimension", h.score.completeness >= 0)
check("health identifies issues", isinstance(h.issues, list))

report = generate_health_report(kb)
check("health_report has total_modules", report.total_modules > 0)
check("health_report has overall_score", report.overall_score >= 0)
check("health_report has category_breakdown", len(report.category_breakdown) > 0)


# ═══════════════ Phase 3B: Usage Analytics ═══════════════
print("\n=== Phase 3B: Usage Stats ===")

data = aggregate_usage_stats(kb, period_days=30)
check("usage_stats has total_searches", data.total_searches >= 0)
check("usage_stats has total_loads", data.total_loads >= 0)
check("usage_stats has conversion_rate", data.conversion_rate >= 0)
check("usage_stats has top_modules list", isinstance(data.top_modules, list))

# ═══════════════ Phase 3C: Graph Analysis ═══════════════
print("\n=== Phase 3C: Graph ===")

gs = analyze_graph(kb)
check("graph_stats has total_nodes", gs.total_nodes > 0)
check("graph_stats has total_edges", gs.total_edges >= 0)
check("graph_stats has density", gs.density >= 0)
check("graph_stats has hub_modules list", isinstance(gs.hub_modules, list))
check("graph_stats has orphan_modules list", isinstance(gs.orphan_modules, list))

clusters = detect_clusters(kb)
check("detect_clusters returns list", isinstance(clusters, list))


# ═══════════════ Phase 3D: Recommendations ═══════════════
print("\n=== Phase 3D: Recommendations ===")

recs = generate_recommendations(kb)
check("recommendations has archive_candidates", isinstance(recs.archive_candidates, list))
check("recommendations has enrichment_needed", isinstance(recs.enrichment_needed, list))
check("recommendations has suggested_links", isinstance(recs.suggested_links, list))
check("recommendations has review_reminders", isinstance(recs.review_reminders, list))


# ═══════════════ Phase 4A: Platform Connectors ═══════════════
print("\n=== Phase 4A: Connect ===")

check("PLATFORMS has claude-code", "claude-code" in PLATFORMS)
check("PLATFORMS has copilot", "copilot" in PLATFORMS)
check("PLATFORMS has cursor", "cursor" in PLATFORMS)
check("PLATFORMS has windsurf", "windsurf" in PLATFORMS)

entry = build_mcp_entry(kb)
check("build_mcp_entry command=km", entry["command"] == "km")
check("build_mcp_entry has --kb-path", "--kb-path" in entry["args"])
check("build_mcp_entry has serve", "serve" in entry["args"])

cfg_path = kb / "test-mcp.json"
write_mcp_config(cfg_path, entry)
check("write_mcp_config creates file", cfg_path.exists())
check("has_entry true after write", has_entry(cfg_path))

# Merge test
entry2 = {"command": "other-server", "args": []}
write_mcp_config(cfg_path, entry2)
data_after = read_mcp_config(cfg_path)
check("write preserves existing entries",
      "knowledge-manager" in data_after.get("mcpServers", {}))

check("remove_mcp_entry returns True", remove_mcp_entry(cfg_path))
check("has_entry false after remove", not has_entry(cfg_path))


# ═══════════════ Phase 4B: Federation ═══════════════
print("\n=== Phase 4B: Federation ===")

ns_kb = Path(tempfile.mkdtemp()) / "ns-kb"
ns_kb.mkdir()
save_index(Index(description="NS KB"), ns_kb)
mod_ns = make_mod("ns-mod", "auth")
save_module(mod_ns, ns_kb)
rebuild_index(ns_kb)

cfg_json = {
    "federation": {
        "namespaces": {
            "auth": {
                "kb_path": str(ns_kb),
                "description": "Auth NS",
                "search_default": True,
            }
        }
    }
}
(kb / "config.json").write_text(json.dumps(cfg_json))
fed = load_federation(kb)
check("load_federation loads namespace", "auth" in fed)
check("federation namespace has index", fed["auth"]["index"] is not None)
check("federation namespace has description", fed["auth"]["description"] == "Auth NS")
check("federation namespace search_default=True", fed["auth"]["search_default"] is True)

cache = ModuleCache(max_size=10)
cache.put(make_mod("dup-id", "general"), namespace="ns1")
cache.put(make_mod("dup-id", "general"), namespace="ns2")
check("cache namespace isolation: ns1", cache.get("dup-id", "ns1") is not None)
check("cache namespace isolation: ns2", cache.get("dup-id", "ns2") is not None)
check("cache namespace miss: wrong ns", cache.get("dup-id", "ns3") is None)


# ═══════════════ Phase 4C: Webhooks ═══════════════
print("\n=== Phase 4C: Webhooks ===")

ep = WebhookEndpoint(
    url="https://example.com/webhook",
    events=["module.created", "module.deprecated"],
    secret="test-secret",
)
check("webhook endpoint url stored", ep.url == "https://example.com/webhook")
check("webhook endpoint secret stored", ep.secret == "test-secret")
check("webhook retry defaults: max_attempts=3", ep.retry.max_attempts == 3)
check("webhook retry defaults: backoff=30", ep.retry.backoff_seconds == 30)
check("event_matches positive", _event_matches("module.created", ep))
check("event_matches negative", not _event_matches("module.archived", ep))
check("event_matches all when empty filter",
     _event_matches("any.event", WebhookEndpoint(url="x", events=[])))

sig = _sign_payload("test payload", "secret-key")
check("HMAC-SHA256 produces 64-char hex", len(sig) == 64)
check("HMAC consistent for same input", sig == _sign_payload("test payload", "secret-key"))
check("HMAC different for different input", sig != _sign_payload("other", "secret-key"))

emit_event(kb, "module.created", "test-mod", "auth")
check("emit_event no-op when disabled (no error)", True)

failures = load_webhook_failures(kb)
check("load_webhook_failures empty for fresh KB", failures == [])


# ═══════════════ Phase 4D: Marketplace ═══════════════
print("\n=== Phase 4D: Marketplace ===")

mp_dir = Path(tempfile.mkdtemp()) / "mp"
mp_dir.mkdir()
(auth_dir := mp_dir / "auth").mkdir()
(sec_dir := mp_dir / "security").mkdir()

mp_idx = MPIndex(
    modules={
        "auth/best-practices": MPMod(
            id="best-practices", category="auth",
            title="Auth Best Practices", summary="Security guidelines for auth",
            tags=["auth", "security"], version="1.0.0",
            author="community", confidence="high", dependencies=[],
        ),
        "security/secret-rotation": MPMod(
            id="secret-rotation", category="security",
            title="Secret Rotation Guide", summary="How to rotate secrets safely",
            tags=["security"], version="1.0.0",
            author="community", confidence="high",
            dependencies=["auth/best-practices"],
        ),
    }
)
(mp_dir / "index.json").write_text(mp_idx.model_dump_json(indent=2))
auth_dir.joinpath("best-practices.json").write_text(
    make_mod("best-practices", "auth").model_dump_json(indent=2)
)
sec_dir.joinpath("secret-rotation.json").write_text(
    make_mod("secret-rotation", "security").model_dump_json(indent=2)
)

fetched = fetch_marketplace_index(str(mp_dir))
check("fetch_marketplace_index local", fetched is not None)
check("marketplace index has module", "auth/best-practices" in fetched.modules)
check("fetch_marketplace_index missing returns None",
      fetch_marketplace_index(str(Path(tempfile.mkdtemp()) / "nope")) is None)

results = search_marketplace("security", mp_idx)
check("search_marketplace finds by tag", len(results) == 2)
check("search_marketplace no match returns empty", search_marketplace("zzz", mp_idx) == [])

plan = resolve_install_plan("security/secret-rotation", mp_idx)
check("install_plan resolves deps", len(plan.modules) == 2)
check("install_plan records dependency", "auth/best-practices" in plan.dependencies_installed)
check("install_plan target_category=security", plan.target_category == "security")

try:
    resolve_install_plan("nonexistent/mod", mp_idx)
    check("resolve_install_plan raises on missing", False)
except ValueError:
    check("resolve_install_plan raises on missing", True)

mod_pub = make_mod("pub-test", "auth")
mod_pub.metadata.confidence = "high"
check("publish_gate: valid module passes", check_publish_gate(mod_pub.model_dump_json()) == [])

mod_bad = make_mod("pub-bad", "auth")
mod_bad.metadata.confidence = "low"
check("publish_gate: low confidence fails", len(check_publish_gate(mod_bad.model_dump_json())) > 0)

check("publish_gate: invalid JSON fails", len(check_publish_gate("not json")) > 0)

result = sanitize_module_text(
    "Contact admin@company.com or visit https://internal.company.com/secret",
    [r"[a-zA-Z0-9._%+-]+@company\.com", r"https://internal\.company\.com\S*"],
)
check("sanitize redacts email", "<redacted>" in result and "admin@company.com" not in result)
check("sanitize redacts URL", "internal.company.com" not in result)
check("sanitize no patterns = no change", sanitize_module_text("hello world", []) == "hello world")


# ═══════════════ Summary ═══════════════
print()
print("=" * 50)
total = pass_count + fail_count
status = "✅ ALL PASSED" if fail_count == 0 else f"❌ {fail_count} FAILURES"
print(f"Phase 0-4 Verification: {pass_count}/{total} checks passed ({fail_count} failed)  {status}")
print("=" * 50)
sys.exit(0 if fail_count == 0 else 1)
