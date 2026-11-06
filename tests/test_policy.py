from knowledge_manager.policy import evaluate_module_policy, merge_agent_routing_policy
from knowledge_manager.schemas import AgentRoutingPolicyConfig, Module, ModuleContent, RoutingPolicyConfig


def _make_module() -> Module:
    return Module(
        id="deploy-guide",
        category="ops",
        title="Deploy Guide",
        summary="Deploy guide for production changes.",
        content=ModuleContent(
            overview="Deploy guide overview for production changes.",
            details="Deploy guide details with enough length for validation coverage.",
        ),
    )


def test_merge_agent_routing_policy_overrides_workspace_defaults():
    base = RoutingPolicyConfig(
        risk_level_allowed_statuses={"high": ["published"]},
        mandatory_companions={"ops": ["policy/change-approval"]},
    )
    override = AgentRoutingPolicyConfig(
        risk_level_allowed_statuses={"high": ["reviewed", "published"]},
        mandatory_companions={"ops": ["policy/security-baseline"]},
    )

    merged = merge_agent_routing_policy(base, override)

    assert merged.risk_level_allowed_statuses["high"] == ["reviewed", "published"]
    assert merged.mandatory_companions["ops"] == ["policy/security-baseline"]


def test_evaluate_module_policy_blocks_stale_modules_and_collects_companions():
    module = _make_module()
    module.metadata.stale_due_to_source_change = True
    policy = RoutingPolicyConfig(
        suppress_stale_sources=True,
        mandatory_companions={"ops": ["policy/change-approval"]},
        risk_level_companions={"high": ["policy/security-baseline"]},
    )

    decision = evaluate_module_policy(
        module,
        policy,
        allowed_statuses={"published"},
        primary_categories=["ops"],
        risk_level="high",
    )

    assert decision.allowed is False
    assert "suppressed_by_policy:stale_source" in decision.reasons
    assert decision.mandatory_companions == [
        "policy/change-approval",
        "policy/security-baseline",
    ]
