# Contributing

1. Open an issue for a substantial behavior change.
2. Create a focused branch and keep knowledge data, credentials, and generated
   logs out of commits.
3. Install with `poetry install`, try `poetry run km demo ./km-demo`, and run
   `poetry run pytest -q`.
4. Run `python -B tools/check_public_surface.py` before opening a pull request.
5. Build the package with `python -m build` when changing packaging or entry
   points.
6. Describe user impact, tests, and any provider calls in the pull request.

New Python modules must pass `poetry run black --check src tests` and
`poetry run mypy src`. Do not add a new module to the legacy mypy override list
without a linked cleanup reason.

Live provider tests are opt-in and require environment variables. Never paste
API keys, tokens, private notes, or production data into issues or pull requests.
