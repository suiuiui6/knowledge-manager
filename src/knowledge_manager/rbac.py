import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("knowledge_manager.rbac")

ROLES = {"admin", "editor", "reviewer", "viewer"}

PERMISSIONS = {
    "module.read": {"admin", "editor", "reviewer", "viewer"},
    "module.write": {"admin", "editor"},
    "module.review": {"admin", "reviewer"},
    "module.delete": {"admin"},
    "config.manage": {"admin"},
    "user.manage": {"admin"},
    "audit.read": {"admin", "reviewer"},
}


class RBACConfig:
    def __init__(
        self,
        users: dict | None = None,
        roles: dict | None = None,
        group_mapping: dict | None = None,
    ):
        self.users = users or {}
        self.roles = roles or {}
        self.group_mapping = group_mapping or {}


def load_rbac_config(kb_path: Path) -> RBACConfig:
    cfg_path = kb_path / "rbac.json"
    if not cfg_path.exists():
        return RBACConfig()

    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    return RBACConfig(
        users=data.get("users", {}),
        roles=data.get("roles", {}),
        group_mapping=data.get("group_mapping", {}),
    )


def save_rbac_config(kb_path: Path, config: RBACConfig) -> None:
    (kb_path / "rbac.json").write_text(
        json.dumps(
            {
                "users": config.users,
                "roles": config.roles,
                "group_mapping": config.group_mapping,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def get_user_role(user: str, kb_path: Path) -> str:
    config = load_rbac_config(kb_path)
    return config.users.get(user, "viewer")


def set_user_role(user: str, role: str, kb_path: Path) -> bool:
    if role not in ROLES:
        return False
    config = load_rbac_config(kb_path)
    config.users[user] = role
    save_rbac_config(kb_path, config)
    return True


def check_permission(user: str, permission: str, kb_path: Path) -> bool:
    role = get_user_role(user, kb_path)
    allowed_roles = PERMISSIONS.get(permission, set())
    return role in allowed_roles


def require_permission(permission: str):
    """Decorator for CLI commands that require a specific permission."""
    def decorator(func):
        func.__rbac_permission__ = permission
        return func
    return decorator


def list_users(kb_path: Path) -> list[dict]:
    config = load_rbac_config(kb_path)
    return [{"user": user, "role": role} for user, role in config.users.items()]


def remove_user(user: str, kb_path: Path) -> bool:
    config = load_rbac_config(kb_path)
    if user in config.users:
        del config.users[user]
        save_rbac_config(kb_path, config)
        return True
    return False


class PermissionChecker:
    def __init__(self, roles: dict | None = None, group_mapping: dict | None = None):
        self.roles = roles or {}
        self.group_mapping = group_mapping or {}

    def resolve_roles(self, groups: list[str]) -> list[str]:
        resolved: list[str] = []
        for group in groups:
            for role in self.group_mapping.get(group, []):
                if role not in resolved:
                    resolved.append(role)
        return resolved

    def can_read_module(self, groups: list[str], module: dict) -> bool:
        for role in self.resolve_roles(groups):
            role_config = self.roles.get(role, {})
            if "module:read" not in role_config.get("permissions", []):
                continue
            scopes = role_config.get("scopes", [])
            if not scopes:
                return True
            category_scope = f"category:{module.get('category', '')}"
            module_scope = f"module:{module.get('category', '')}/{module.get('id', '')}"
            if category_scope in scopes or module_scope in scopes:
                return True
        return False
