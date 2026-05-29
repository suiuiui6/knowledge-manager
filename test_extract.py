#!/usr/bin/env python3
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))

from knowledge_manager.schemas import Config, ExtractionConfig
from knowledge_manager.llm_clients import create_client
from knowledge_manager.extractor import Extractor

def load_config(kb_path: Path) -> Config:
    config_path = kb_path / "config.json"
    if not config_path.exists():
        return Config()
    return Config.model_validate_json(config_path.read_text(encoding="utf-8"))

async def main():
    print("Starting test...")
    kb = Path("D:/tyh/knowledge_base")
    print("Loading config...")
    cfg = load_config(kb)
    print("Getting provider...")
    provider_name, provider_cfg = cfg.get_default_provider()
    print(f"Provider: {provider_name}")

    print("Creating client...")
    client = create_client(provider_name, provider_cfg)
    print("Creating extractor...")
    extractor = Extractor(client, cfg.extraction)

    # Small test text
    text = """
# OAuth 2.0 Flow

OAuth 2.0 is an authorization framework. The authorization code flow involves:
1. User clicks "Login with Provider"
2. Redirect to provider's authorization endpoint
3. User grants permission
4. Provider redirects back with authorization code
5. Exchange code for access token

The access token is then used to make API requests on behalf of the user.
"""

    print("Extracting from test text...")
    print("Calling LLM...")
    try:
        modules = await extractor.extract(text, "auth")
        print(f"LLM returned, parsing...")
    except Exception as e:
        print(f"Error during extraction: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"\nExtracted {len(modules)} modules")
    for m in modules:
        print(f"  - {m.id}: {m.title}")
