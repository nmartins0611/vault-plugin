#!/usr/bin/env bash
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_DIR="$(cd "$DEMO_DIR/.." && pwd)"
ENV_FILE="$DEMO_DIR/.env"
OUT_DIR="$DEMO_DIR/out"
RECEIPT="$OUT_DIR/secret-change.json"
RULEBOOK_LOG="$OUT_DIR/rulebook.log"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE is missing. Copy demo/.env.example to demo/.env and fill in Vault credentials." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

mkdir -p "$OUT_DIR"
rm -f "$RECEIPT" "$RULEBOOK_LOG"

python3 "$DEMO_DIR/scripts/prepare_vault.py"

echo "[INFO] Starting ansible-rulebook..."
cd "$DEMO_DIR"
export DEMO_RECEIPT="$RECEIPT"
export ANSIBLE_CONFIG="$DEMO_DIR/ansible.cfg"
export ANSIBLE_BECOME=false
ansible-rulebook \
    -i "$DEMO_DIR/inventory.yml" \
    -r "$DEMO_DIR/rulebook.yml" \
    -S "$DEMO_DIR/plugins" \
    -E DEMO_RECEIPT \
    --print-events \
    -vv \
    >"$RULEBOOK_LOG" 2>&1 &
RULEBOOK_PID=$!

cleanup() {
    if kill -0 "$RULEBOOK_PID" 2>/dev/null; then
        kill "$RULEBOOK_PID" 2>/dev/null || true
        wait "$RULEBOOK_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

echo "[INFO] Waiting for rulebook to start (pid $RULEBOOK_PID)..."
for _ in $(seq 1 60); do
    if grep -q "Tailing Vault audit log via SSH" "$RULEBOOK_LOG" 2>/dev/null; then
        break
    fi
    if ! kill -0 "$RULEBOOK_PID" 2>/dev/null; then
        echo "ERROR: ansible-rulebook exited during startup" >&2
        cat "$RULEBOOK_LOG" >&2
        exit 1
    fi
    sleep 1
done

if ! grep -q "Tailing Vault audit log via SSH" "$RULEBOOK_LOG"; then
    echo "ERROR: rulebook did not start tailing the audit log" >&2
    cat "$RULEBOOK_LOG" >&2
    exit 1
fi

echo "[INFO] Writing demo secret to ${VAULT_ADDR}..."
python3 "$DEMO_DIR/scripts/trigger_secret.py" write

echo "[INFO] Waiting for EDA receipt..."
for _ in $(seq 1 20); do
    if [[ -f "$RECEIPT" ]]; then
        echo "[INFO] EDA handled the Vault event:"
        cat "$RECEIPT"
        echo
        echo "[INFO] Rulebook log: $RULEBOOK_LOG"
        exit 0
    fi
    sleep 1
done

echo "ERROR: No receipt written. Rulebook log:" >&2
cat "$RULEBOOK_LOG" >&2
exit 1
