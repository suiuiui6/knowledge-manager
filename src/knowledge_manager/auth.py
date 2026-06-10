import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("knowledge_manager.auth")


class AuthConfig:
    def __init__(self, provider: str = "", oidc_config: dict | None = None):
        self.provider = provider
        self.oidc_config = oidc_config or {}


def load_auth_config(kb_path: Path) -> Optional[AuthConfig]:
    cfg_path = kb_path / "auth.json"
    if not cfg_path.exists():
        return None
    import json
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    return AuthConfig(
        provider=data.get("provider", ""),
        oidc_config=data.get("oidc_config"),
    )


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, kb_path: Path):
        super().__init__(app)
        self.kb_path = kb_path
        self.auth_config = load_auth_config(kb_path)

    async def dispatch(self, request: Request, call_next):
        if self.auth_config is None or not self.auth_config.provider:
            return await call_next(request)

        public_paths = {"/api/health", "/ui/fallback", "/docs", "/openapi.json"}
        if request.url.path in public_paths:
            return await call_next(request)

        if self.auth_config.provider == "oidc":
            user = await self._verify_oidc(request)
        elif self.auth_config.provider == "token":
            user = self._verify_token(request)
        else:
            return await call_next(request)

        if user is None:
            return JSONResponse(status_code=401, content={"detail": "Authentication required"})

        request.state.user = user
        return await call_next(request)

    async def _verify_oidc(self, request: Request) -> Optional[str]:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[7:]
        try:
            payload = self._decode_jwt_unsigned(token)
            return payload.get("sub") or payload.get("email", "unknown")
        except Exception:
            logger.warning("OIDC token verification failed", exc_info=True)
            return None

    def _verify_token(self, request: Request) -> Optional[str]:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[7:]
        cfg = self.auth_config.oidc_config if self.auth_config else {}
        expected = cfg.get("static_token", "")
        if expected and token == expected:
            return "token-user"
        return None

    @staticmethod
    def _decode_jwt_unsigned(token: str) -> dict:
        import base64, json
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        payload += "=" * (4 - len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))


def inject_auth_middleware(app, kb_path: Path) -> None:
    auth_config = load_auth_config(kb_path)
    if auth_config and auth_config.provider:
        app.add_middleware(AuthMiddleware, kb_path=kb_path)
        logger.info("Auth middleware injected: provider=%s", auth_config.provider)
