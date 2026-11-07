# Release checklist

## Local preflight

```bash
poetry run pytest -q
poetry run black --check src tests scripts
poetry run mypy src
python -B tools/check_public_surface.py
python -m build
```

Install the built wheel in a clean environment and run:

```bash
km --version
km demo .release-demo
km --kb-path .release-demo search "rollback deployment"
```

## GitHub release

The default branch and release must point at the same verified commit. Create a
tag and release only after the CI run for that commit is green:

```bash
git tag -a v0.6.0 -m "v0.6.0"
git push origin v0.6.0
gh release create v0.6.0 --generate-notes
```

## PyPI publication

The repository is buildable, but publication requires a maintainer-owned PyPI
token. Do not commit the token. After authentication:

```bash
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

Until the package is published, the README uses the Git install path with `uv`
or `pipx`. After publication, replace that path with the PyPI one-liner and add
the PyPI badge.

## Social preview

GitHub does not expose a stable public API for uploading a repository social
preview. Upload `docs/assets/social-preview.png` manually in the repository
settings after the public description and topics are updated.

## Evidence to keep

- The tested commit SHA.
- The exact command and exit code.
- The CI run URL.
- The built artifact name or a checksum.
- Any external action that was intentionally not run.
