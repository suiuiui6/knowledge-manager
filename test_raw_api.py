#!/usr/bin/env python3
import asyncio
import httpx
import json

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
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": "Bearer <redacted-api-key>"},
            timeout=60,
        )
        print(f"Status: {resp.status_code}")
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        print(f"Response length: {len(content)} chars")
        print(f"Response:\n{content}")

if __name__ == "__main__":
    asyncio.run(main())
