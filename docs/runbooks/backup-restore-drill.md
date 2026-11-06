# Backup And Restore Drill

## Create A Bundle

```bash
RELEASE_DIR=/opt/knowledge-manager/release-artifacts/run-$(date +%Y%m%d%H%M%S)
install -d -o km -g km "$RELEASE_DIR"
BUNDLE_PATH=$(/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb backup create --output-dir "$RELEASE_DIR")
```

If the drill is being run against a release candidate that already has fresh readiness evidence, attach it to the backup bundle:

```bash
BUNDLE_PATH=$(/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb backup create --output-dir "$RELEASE_DIR" --attach "$RELEASE_DIR"/verify-production-readiness.json --attach "$RELEASE_DIR"/verify-deployment.json --attach "$RELEASE_DIR"/verify-install-smoke.json)
```

## Restore Into An Empty Target

```bash
install -d /opt/knowledge-manager/restore-kb
/opt/knowledge-manager/.venv/bin/km backup restore --bundle "$BUNDLE_PATH" --target-kb /opt/knowledge-manager/restore-kb
```

## Verify

```bash
find /opt/knowledge-manager/restore-kb -maxdepth 2 -type f
/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/restore-kb verify-deployment --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json> --format json > "$RELEASE_DIR"/restore-verify-deployment.json
```

## Drill Policy

- Run the backup/restore drill at least once every 30 days.
- Store `"$BUNDLE_PATH"` and `"$RELEASE_DIR"/restore-verify-deployment.json` with the release record.
