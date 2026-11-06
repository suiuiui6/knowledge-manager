# Contributing

1. Open an issue for a substantial behavior change.
2. Create a focused branch and keep knowledge data, credentials, and generated
   logs out of commits.
3. Install with `poetry install` and run `poetry run pytest -q`.
4. Run `python -B tools/check_public_surface.py` before opening a pull request.
5. Describe user impact, tests, and any provider calls in the pull request.

Live provider tests are opt-in and require environment variables. Never paste
API keys, tokens, private notes, or production data into issues or pull requests.
