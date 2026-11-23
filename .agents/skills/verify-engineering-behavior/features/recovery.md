# Task recovery

## Sub-features

Failed extraction preserves input, explicit retry stages a valid module and metadata, successful completion removes consumed input. Expired takeover rejects old attempts.

## How to get to it (user POV)

Queued upload/source jobs are processed by `km worker run`; recovery uses persisted state and leases rather than process presence.

## Driving it with the helper

The helper runs scripts/run_ingestion_recovery_drill.py in an empty isolated KB. Inspect recovery.json for completed state, input preservation, staged_module_valid and staging_metadata_present. Run tests/test_reliability.py and tests/test_worker_service.py for actual multiprocess takeover and live-loop expiry recovery.

## Gotchas

The recovery drill deliberately replaces the external extraction provider. It does not prove network behavior, liveness under a stopped worker or exactly-once external execution. An empty KB is mandatory; never point the drill at user data.
