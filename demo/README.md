# Vault + EDA demo (vault.nostromo.io)

This demo reacts to secret writes on the homelab Vault at `http://vault.nostromo.io:8200`.

That Vault is Community / OpenBao 2.0.4. The Events WebSocket API (`/v1/sys/events/subscribe/...`) is Enterprise-only and returns `unsupported path` here. The demo therefore uses a **file audit device** on the Vault host and tails it over SSH into ansible-rulebook.

```
vault kv put secret/eda-demo/app ...
        -> file audit on vault.nostromo.io
        -> ssh tail -F /opt/vault/logs/audit.json
        -> ansible-rulebook
        -> demo/out/secret-change.json
```

## Prerequisites

- `ansible-rulebook` and Java (already needed by EDA)
- SSH as `root@vault.nostromo.io` with a key (BatchMode)
- Vault root token and unseal key in `demo/.env` (not committed)

## Setup

```bash
cp demo/.env.example demo/.env
# fill VAULT_TOKEN and VAULT_UNSEAL_KEY
chmod 600 demo/.env
```

## Run

```bash
./demo/scripts/run_demo.sh
```

That script unseals Vault if needed, enables the file audit device, starts the rulebook, writes `secret/eda-demo/app`, and waits for `demo/out/secret-change.json`.

Manual pieces:

```bash
python3 demo/scripts/prepare_vault.py
ansible-rulebook -i demo/inventory.yml -r demo/rulebook.yml -S demo/plugins --print-events -vv
# in another terminal:
python3 demo/scripts/trigger_secret.py write
```

## On aap.nostromo.io

The demo runs as user service `vault-eda-demo` on the AAP host (ansible-rulebook in the AAP 2.7 decision environment image). It is not a Gateway EDA activation.

**Terminal 1 — watch events:**

```bash
ssh srvadmin@aap.nostromo.io
export XDG_RUNTIME_DIR=/run/user/1000
podman logs -f vault-eda-demo
```

**Terminal 2 — generate events (from your laptop):**

```bash
cd /home/nmartins/Development/AI-Assisted/vault-plugin
python3 demo/scripts/trigger_secret.py write
python3 demo/scripts/trigger_secret.py delete
```

Receipt on AAP: `/home/srvadmin/vault-eda-demo/out/secret-change.json`

Service control:

```bash
ssh srvadmin@aap.nostromo.io
export XDG_RUNTIME_DIR=/run/user/1000
systemctl --user status vault-eda-demo
systemctl --user restart vault-eda-demo
```

## Why not `hashicorp.vault.vault_events`?

That plugin is correct for Vault Enterprise / HCP. This lab Vault is community and has no Events API. Do not point the WebSocket plugin at `vault.nostromo.io` and expect it to connect.
