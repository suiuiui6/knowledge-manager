#!/usr/bin/env python3
"""Debug search scoring for 'auth' query."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
from knowledge_manager.storage import save_module, search_modules
import tempfile
import re

# Create test KB
kb_path = Path(tempfile.mkdtemp())

jwt = Module(
    id="jwt", category="auth",
    title="JWT signing and validation",
    summary="Issuing and validating JSON Web Tokens with RS256",
    content=ModuleContent(
        overview="A JWT is a compact token signed with RS256.",
        details="Signing uses an RSA private key; gateways validate via JWKS.",
    ),
    metadata=ModuleMetadata(tags=["jwt", "authentication", "rs256"]),
)

conn_pool = Module(
    id="conn-pool", category="database",
    title="Database connection pooling",
    summary="Sizing and lifecycle of database connection pools for Postgres",
    content=ModuleContent(
        overview="Pool keeps connections so requests skip the TCP+TLS+auth handshake.",
        details="Right-size the pool; Postgres prefers a small number of busy connections.",
    ),
    metadata=ModuleMetadata(tags=["database", "postgres", "performance"]),
)

save_module(jwt, kb_path)
save_module(conn_pool, kb_path)

# Manual scoring
FIELD_WEIGHTS = {"title": 5, "tag": 3, "summary": 2, "overview": 1}

def score_module(module, query_term):
    word_boundary = re.compile(rf"\b{re.escape(query_term)}\b", re.IGNORECASE)
    partial = re.compile(re.escape(query_term), re.IGNORECASE) if len(query_term) < 5 else None

    score = 0
    matches = []

    # Word boundary checks
    if word_boundary.search(module.title):
        score += FIELD_WEIGHTS["title"]
        matches.append(f"title (word boundary): +{FIELD_WEIGHTS['title']}")
    elif any(word_boundary.search(tag) for tag in module.metadata.tags):
        score += FIELD_WEIGHTS["tag"]
        matches.append(f"tag (word boundary): +{FIELD_WEIGHTS['tag']}")
    elif word_boundary.search(module.summary):
        score += FIELD_WEIGHTS["summary"]
        matches.append(f"summary (word boundary): +{FIELD_WEIGHTS['summary']}")
    elif word_boundary.search(module.content.overview):
        score += FIELD_WEIGHTS["overview"]
        matches.append(f"overview (word boundary): +{FIELD_WEIGHTS['overview']}")

    # Partial match fallback
    if score == 0 and partial:
        if partial.search(module.title):
            score += FIELD_WEIGHTS["title"] // 2
            matches.append(f"title (partial): +{FIELD_WEIGHTS['title'] // 2}")
        elif any(partial.search(tag) for tag in module.metadata.tags):
            score += FIELD_WEIGHTS["tag"] // 2
            matches.append(f"tag (partial): +{FIELD_WEIGHTS['tag'] // 2}")
        elif partial.search(module.summary):
            score += FIELD_WEIGHTS["summary"] // 2
            matches.append(f"summary (partial): +{FIELD_WEIGHTS['summary'] // 2}")
        elif partial.search(module.content.overview):
            score += FIELD_WEIGHTS["overview"] // 2
            matches.append(f"overview (partial): +{FIELD_WEIGHTS['overview'] // 2}")

    return score, matches

print("=== Manual Scoring for 'auth' ===\n")

jwt_score, jwt_matches = score_module(jwt, "auth")
print(f"JWT module:")
print(f"  Score: {jwt_score}")
print(f"  Matches: {jwt_matches}")
print(f"  Tags: {jwt.metadata.tags}")
print()

cp_score, cp_matches = score_module(conn_pool, "auth")
print(f"CONN-POOL module:")
print(f"  Score: {cp_score}")
print(f"  Matches: {cp_matches}")
print(f"  Overview: {conn_pool.content.overview}")
print()

print("=== Actual search_modules() result ===")
results = search_modules("auth", kb_path)
for i, m in enumerate(results):
    print(f"{i+1}. {m.id}")
