#!/usr/bin/env python3
import asyncio
import httpx
import json
import os

async def main():
    print("Testing DeepSeek API with extraction prompt...")

    prompt = """You are a knowledge extraction assistant. Extract structured knowledge modules from the raw text below.

Category: test

Raw text:
OAuth 2.0 is an authorization framework. The authorization code flow involves redirecting to provider.

Return a JSON array (no markdown, no explanation) of up to 10 modules. Each module:
{
  "id": "kebab-case-id",
  "title": "Concise title (5+ chars)",
  "summary": "One sentence summary (10-500 chars)",
  "content": {
    "overview": "High-level explanation (10+ chars)",
    "details": "Technical details (20+ chars)",
    "examples": "",
    "references": "",
    "caveats": ""
  },
  "metadata": {
    "tags": ["tag1", "tag2"],
    "confidence": "high"
  }
}
"""

    url = "https://api.deepseek.com/v1/chat/completions"
    payload = {
        "model": "deepseek-v4-pro",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 4096,
    }

    print("Sending request...")
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("Set DEEPSEEK_API_KEY before running this live API smoke test.")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
        )
        print(f"Status: {resp.status_code}")
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        print(f"Response length: {len(content)} chars")
        print(f"Response:\n{content}")

if __name__ == "__main__":
    asyncio.run(main())
