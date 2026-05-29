#!/usr/bin/env python3
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))

from knowledge_manager.schemas import Config
from knowledge_manager.llm_clients import create_client

def load_config(kb_path: Path) -> Config:
    config_path = kb_path / "config.json"
    if not config_path.exists():
        return Config()
    return Config.model_validate_json(config_path.read_text(encoding="utf-8"))

async def main():
    kb = Path("D:/tyh/knowledge_base")
    cfg = load_config(kb)
    provider_name, provider_cfg = cfg.get_default_provider()

    print(f"Provider: {provider_name}")
    print(f"Model: {provider_cfg.model}")
    print(f"Base URL: {provider_cfg.base_url}")
    print()

    client = create_client(provider_name, provider_cfg)

    prompt = "Return a JSON array with one object: {\"test\": \"hello\"}. No markdown, just JSON."

    print("Sending test prompt...")
    try:
        response = await client.complete(prompt)
        print(f"Response length: {len(response)} chars")
        print(f"Response:\n{response}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
