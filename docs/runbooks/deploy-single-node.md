# Single-Node Deployment

## Prerequisites

On Rocky Linux 9 / EL9, install the base packages first:

```bash
dnf install -y python3.11 git caddy logrotate
```

## Install

```bash
git clone <repo-url> /opt/knowledge-manager
cd /opt/knowledge-manager
git checkout <release-ref>
getent group km >/dev/null || groupadd --system km
id -u km >/dev/null 2>&1 || useradd --system --home /opt/knowledge-manager --shell /sbin/nologin --gid km km
install -d -o km -g km /opt/knowledge-manager /opt/knowledge-manager/kb /opt/knowledge-manager/release-artifacts /var/log/knowledge-manager
chown -R km:km /opt/knowledge-manager /var/log/knowledge-manager
python3.11 -m venv /opt/knowledge-manager/.venv
/opt/knowledge-manager/.venv/bin/pip install --upgrade pip
/opt/knowledge-manager/.venv/bin/pip install --no-cache-dir --force-reinstall .
/opt/knowledge-manager/.venv/bin/km --version
/opt/knowledge-manager/.venv/bin/km init /opt/knowledge-manager/kb
install -m 0644 deploy/systemd/knowledge-manager-api.service /etc/systemd/system/knowledge-manager-api.service
install -m 0644 deploy/systemd/knowledge-manager-worker.service /etc/systemd/system/knowledge-manager-worker.service
install -m 0644 deploy/caddy/Caddyfile /etc/caddy/Caddyfile
install -m 0644 deploy/logrotate/knowledge-manager /etc/logrotate.d/knowledge-manager
install -m 0644 .env.production.example /opt/knowledge-manager/.env.production
echo "Review /opt/knowledge-manager/.env.production and confirm KM_KB_PATH, KM_UI_HOST, KM_UI_PORT, and KM_LOG_LEVEL before starting services."
systemctl daemon-reload
systemctl enable --now caddy
systemctl enable --now knowledge-manager-api knowledge-manager-worker
systemctl reload caddy
```

For an existing deployment with a populated KB, keep the existing `/opt/knowledge-manager/kb` tree or restore it from a known-good backup instead of re-running `km init`.

Before exposing the service publicly, replace the placeholder host in `deploy/caddy/Caddyfile` with your real domain and keep the site label scheme-free so Caddy can manage automatic HTTPS for the real site.

## Verify

```bash
RELEASE_DIR=/opt/knowledge-manager/release-artifacts/run-$(date +%Y%m%d%H%M%S)
install -d -o km -g km "$RELEASE_DIR"
/opt/knowledge-manager/.venv/bin/km --version
/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb stats
python3.11 /opt/knowledge-manager/scripts/verify_install_smoke.py --project-root /opt/knowledge-manager --python python3.11 --format json > "$RELEASE_DIR"/verify-install-smoke.json
python3.11 /opt/knowledge-manager/scripts/verify_install_smoke.py --project-root /opt/knowledge-manager --python python3.11 --format text
systemctl status caddy
systemctl status knowledge-manager-api
systemctl status knowledge-manager-worker
curl -fsS http://127.0.0.1:8420/api/ready
curl -fsS http://127.0.0.1:8420/api/metrics
/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb verify-production-readiness --matrix-summary <fresh-matrix-summary.json> > "$RELEASE_DIR"/verify-production-readiness.json
/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb verify-deployment --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json> --format json > "$RELEASE_DIR"/verify-deployment.json
/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb support bundle --output-dir "$RELEASE_DIR" --matrix-summary <fresh-matrix-summary.json>
python3.11 /opt/knowledge-manager/scripts/collect_host_deploy_proof.py --output-dir "$RELEASE_DIR"
python3.11 /opt/knowledge-manager/scripts/verify_release_artifacts.py --release-dir "$RELEASE_DIR"
python3.11 /opt/knowledge-manager/scripts/collect_release_evidence.py --release-dir "$RELEASE_DIR" --kb-path /opt/knowledge-manager/kb --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json>
# verify-release-artifacts.json is written into $RELEASE_DIR by verify_release_artifacts.py
systemctl cat knowledge-manager-api > "$RELEASE_DIR"/knowledge-manager-api.unit.txt
systemctl cat knowledge-manager-worker > "$RELEASE_DIR"/knowledge-manager-worker.unit.txt
caddy validate --config /etc/caddy/Caddyfile > "$RELEASE_DIR"/caddy-validate.txt 2>&1
logrotate -d /etc/logrotate.d/knowledge-manager > "$RELEASE_DIR"/logrotate-check.txt 2>&1
```

## Infrastructure Verification

```bash
systemctl status knowledge-manager-api
systemctl status knowledge-manager-worker
systemctl cat knowledge-manager-api > "$RELEASE_DIR"/knowledge-manager-api.unit.txt
systemctl cat knowledge-manager-worker > "$RELEASE_DIR"/knowledge-manager-worker.unit.txt
caddy validate --config /etc/caddy/Caddyfile > "$RELEASE_DIR"/caddy-validate.txt 2>&1
logrotate -d /etc/logrotate.d/knowledge-manager > "$RELEASE_DIR"/logrotate-check.txt 2>&1
```

## Rollback

```bash
systemctl stop knowledge-manager-api knowledge-manager-worker
mv /opt/knowledge-manager/kb /opt/knowledge-manager/kb.rollback.$(date +%Y%m%d%H%M%S)
install -d -o km -g km /opt/knowledge-manager/kb
/opt/knowledge-manager/.venv/bin/km backup restore --bundle <known-good-backup.zip> --target-kb /opt/knowledge-manager/kb
systemctl start knowledge-manager-api knowledge-manager-worker
/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb verify-deployment --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json> --format json
```
