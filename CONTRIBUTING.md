# Contributing

1. Open an issue for a substantial behavior change.
2. Create a focused branch and keep knowledge data, credentials, and generated
   logs out of commits.
3. Use Python 3.10 or 3.12 and Poetry 2.4.1. Run `poetry check --lock`, then
   `poetry install --no-interaction`, try `poetry run km demo ./km-demo`, and
   run `poetry run pytest -q`. Do not install newer dependencies over the lock.
4. Run `python -B tools/check_public_surface.py` before opening a pull request.
5. Build the package with `python -m build` when changing packaging or entry
   points.
6. Describe user impact, tests, and any provider calls in the pull request.

CI tests the same lock file on Python 3.10 and 3.12 and uploads the runtime,
lock hash, installed dependencies and pytest report. Any test process failure,
including a crash after a report is written, fails the job. Formatting and types
run as separate blocking jobs; branch protection must be configured separately.
The historical non-blocking static-report choice in the October CI plan is
superseded by these gates. The manual M-scale evidence job remains non-blocking
while its known crash is unresolved.

`python scripts/verify_install_smoke.py` builds a wheel and installs it in a
separate empty environment before exercising the CLI. This checks distribution
installation with resolver-selected dependencies; it does not replace locked
regression tests. Captured Python subprocess output uses UTF-8 on both sides;
unhandled thread exceptions fail pytest.

New Python modules must pass `poetry run black --check src tests scripts` and
`poetry run mypy src`. Do not add a new module to the legacy mypy override list
under any cleanup pretext. The changed storage, HTTP and job execution modules
are checked in full; remaining entries describe existing typing debt.

Live provider tests are opt-in and require environment variables. Never paste
API keys, tokens, private notes, or production data into issues or pull requests.
