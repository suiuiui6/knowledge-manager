# Public surface evidence

This file records the evidence used by the public README. Update it when the
tested commit changes; do not treat an older run as proof for a newer snapshot.

## 2026-11-07 local verification

Commands run against the final local snapshot:

```text
python -B -m pytest -q                 869 passed
python -B tools/check_public_surface.py PASS
python -m build --no-isolation         sdist + wheel built
```

The built wheel was extracted into a clean directory and exercised with:

```text
python -m knowledge_manager.cli --version             km, version 0.6.0
python -m knowledge_manager.cli demo <path>          4 approved modules, 1 staged draft
python -m knowledge_manager.cli --kb-path <path> search "rollback deployment"
                                                       agent-workflows/rollback-deployment
```

## Scope

- The demo does not call an external LLM provider.
- The default CI does not call live providers.
- Hosted deployment, high-scale semantic retrieval, and production SLAs are not
  verified by these commands.
- The clean-venv `scripts/verify_install_smoke.py` run was attempted but did not
  complete because dependency installation stalled in the restricted network.
  The built wheel itself was extracted and exercised successfully; CI performs
  the clean install in its own environment.
