import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("knowledge_manager.auth")


class AuthError(RuntimeError):
    pass


class AuthConfig:
    def __init__(self, provider: str = "", oidc_config: dict | None = None):
        self.provider = provider
        self.oidc_config = oidc_config or {}


class AuthSubject(BaseModel):
    user: str
    tenant_id: str = ""
    workspace_id: str = ""
    groups: list[str] = Field(default_factory=list)


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

        public_paths = {"/api/health", "/api/ready", "/api/metrics", "/ui/fallback", "/docs", "/openapi.json"}
        if request.url.path in public_paths:
            return await call_next(request)

        if self.auth_config.provider == "oidc":
            subject = await self._verify_oidc(request)
        elif self.auth_config.provider == "token":
            subject = self._verify_token(request)
        else:
            return JSONResponse(
                status_code=503,
                content={"detail": f"Unsupported authentication provider: {self.auth_config.provider}"},
            )

        if subject is None:
            return JSONResponse(status_code=401, content={"detail": "Authentication required"})

        request.state.user = subject.user
        request.state.auth_subject = subject
        return await call_next(request)

    async def _verify_oidc(self, request: Request) -> Optional[AuthSubject]:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[7:]
        try:
            cfg = self.auth_config.oidc_config if self.auth_config else {}
            payload = validate_oidc_token(
                token,
                issuer=cfg.get("issuer", ""),
                audience=cfg.get("audience"),
                secret=cfg.get("shared_secret") or os.environ.get(cfg.get("shared_secret_env", ""), ""),
                jwks=cfg.get("jwks"),
            )
            return AuthSubject(
                user=payload.get("sub") or payload.get("email", "unknown"),
                tenant_id=payload.get("tenant_id", ""),
                workspace_id=payload.get("workspace_id", ""),
                groups=payload.get("groups", []),
            )
        except Exception:
            logger.warning("OIDC token verification failed", exc_info=True)
            return None

    def _verify_token(self, request: Request) -> Optional[AuthSubject]:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[7:]
        cfg = self.auth_config.oidc_config if self.auth_config else {}
        token_map = cfg.get("static_tokens", {})
        if token in token_map:
            payload = token_map[token]
            return AuthSubject(
                user=payload.get("sub") or payload.get("user") or "token-user",
                tenant_id=payload.get("tenant_id", ""),
                workspace_id=payload.get("workspace_id", ""),
                groups=payload.get("groups", []),
            )
        expected = cfg.get("static_token", "")
        if expected and token == expected:
            return AuthSubject(user="token-user")
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


def validate_oidc_token(
    token: str,
    *,
    issuer: str = "",
    audience: str | None = None,
    secret: str = "",
    jwks: dict | None = None,
) -> dict:
    import jwt

    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:
        raise AuthError("invalid token header") from exc

    algorithm = header.get("alg", "")
    if not algorithm or algorithm.lower() == "none":
        raise AuthError("unsigned tokens are not allowed")

    key = None
    if jwks:
        key_id = header.get("kid")
        for candidate in jwks.get("keys", []):
            if candidate.get("kid") == key_id:
                key = jwt.algorithms.RSAAlgorithm.from_jwk(candidate)
                break
        if key is None:
            raise AuthError("signing key not found")
    elif secret:
        key = secret
    else:
        raise AuthError("no verification key configured")

    options = {"verify_aud": audience is not None, "verify_iss": bool(issuer)}
    try:
        return jwt.decode(
            token,
            key=key,
            algorithms=[algorithm],
            issuer=issuer or None,
            audience=audience,
            options=options,
        )
    except Exception as exc:
        raise AuthError("token validation failed") from exc
