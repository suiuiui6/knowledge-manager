# Eval Gate

Use this gate before enabling a new connector, policy change, or agent rollout.

1. Prepare an eval suite JSON with representative high-risk and normal cases.
2. Run `PYTHONPATH=src python -m pytest tests/test_eval_runner.py tests/test_cli.py -k eval -q`.
3. Run `km --kb-path <kb-path> eval run <suite.json>`.
4. Check these outputs:
   `Hit rate`
   `Suppression-driven failure rate`
   `Baseline win rate`
   `False-positive rate`
   `False-negative rate`
   `policy_failures=... retrieval_failures=...`
5. Block rollout if policy failures spike after a routing-policy change.
6. Block rollout if retrieval failures spike after ingestion or provenance changes.
7. Save the eval suite and output alongside the release evidence.
