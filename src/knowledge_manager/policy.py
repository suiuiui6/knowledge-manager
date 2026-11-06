from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from knowledge_manager.schemas import AgentRoutingPolicyConfig, Module, RoutingPolicyConfig


@dataclass
class PolicyDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    mandatory_companions: list[str] = field(default_factory=list)


def merge_agent_routing_policy(
    base: RoutingPolicyConfig, override: AgentRoutingPolicyConfig | None
) -> RoutingPolicyConfig:
    if override is None:
        return base
    return RoutingPolicyConfig(
        category_priorities={**base.category_priorities, **override.category_priorities},
        task_type_category_priorities={
            **base.task_type_category_priorities,
            **override.task_type_category_priorities,
        },
        task_type_allowed_statuses={
            **base.task_type_allowed_statuses,
            **override.task_type_allowed_statuses,
        },
        mandatory_companions={**base.mandatory_companions, **override.mandatory_companions},
        risk_level_companions={**base.risk_level_companions, **override.risk_level_companions},
        risk_level_allowed_statuses={
            **base.risk_level_allowed_statuses,
            **override.risk_level_allowed_statuses,
        },
        suppress_stale_sources=(
            override.suppress_stale_sources
            if override.suppress_stale_sources is not None
            else base.suppress_stale_sources
        ),
        suppress_expired=(
            override.suppress_expired
            if override.suppress_expired is not None
            else base.suppress_expired
        ),
        agent_overrides=base.agent_overrides,
    )


def evaluate_module_policy(
    module: Module | None,
    policy: RoutingPolicyConfig,
    *,
    allowed_statuses: set[str] | None = None,
    primary_categories: list[str] | None = None,
    risk_level: str | None = None,
) -> PolicyDecision:
    reasons: list[str] = []
    if module is not None and allowed_statuses is not None and module.metadata.status not in allowed_statuses:
        reasons.append(f"suppressed_by_policy:status:{module.metadata.status}")
    if module is not None and policy.suppress_stale_sources and module.metadata.stale_due_to_source_change:
        reasons.append("suppressed_by_policy:stale_source")
    if module is not None and policy.suppress_expired:
        now = datetime.now(timezone.utc)
        if module.metadata.expires_at is not None and module.metadata.expires_at <= now:
            reasons.append("suppressed_by_policy:expired")

    companions: list[str] = []
    for category in primary_categories or []:
        companions.extend(policy.mandatory_companions.get(category, []))
    if risk_level:
        companions.extend(policy.risk_level_companions.get(risk_level, []))

    deduped_companions: list[str] = []
    for companion in companions:
        if companion not in deduped_companions:
            deduped_companions.append(companion)
    return PolicyDecision(
        allowed=not reasons,
        reasons=reasons,
        mandatory_companions=deduped_companions,
    )
