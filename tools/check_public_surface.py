"""Check the minimum safe public surface without third-party dependencies."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ["README.md", "LICENSE", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md"]
README_MARKERS = ["Quick Start", "Contributing", "Security", "License"]
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC|PRIVATE) KEY-----"),
]


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED:
        if not (ROOT / path).is_file():
            errors.append(f"missing required file: {path}")
    readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").is_file() else ""
    for marker in README_MARKERS:
        if marker.lower() not in readme.lower():
            errors.append(f"README missing marker: {marker}")
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True)
    for raw_name in result.stdout.decode().split("\0"):
        if not raw_name:
            continue
        name = raw_name.replace("\\", "/")
        base = Path(name).name.lower()
        if (base == ".env" or (base.startswith(".env.") and base != ".env.example")) or base.endswith((".pem", ".key", ".log")):
            errors.append(f"forbidden tracked path: {name}")
            continue
        path = ROOT / Path(name)
        if not path.is_file():
            continue
        text = path.read_bytes().decode("utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            errors.append(f"credential-like content in: {name}")
    if errors:
        print("public surface check: FAIL")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("public surface check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
