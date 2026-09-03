# Vault + EDA Demo (vault.nostromo.io)

This demo reacts to secret writes on the homelab Vault at `http://vault.nostromo.io:8200` and automatically rotates passwords across an application server and a database.

That Vault is Community / OpenBao 2.0.4. The Events WebSocket API (`/v1/sys/events/subscribe/...`) is Enterprise-only. The demo therefore uses a **file audit device** on the Vault host and tails it over SSH into `ansible-rulebook`.

## Topology

* **`vault.nostromo.io`**: HashiCorp Vault (OpenBao) instance generating events via file audit.
* **`aap.nostromo.io`**: Ansible Automation Platform running the EDA rulebook (`ansible-rulebook`) as a service.
* **`rhel01.nostromo.io`**: Mock application server that reads configuration from `/etc/myapp/config.ini`.
* **`rhel03.nostromo.io`**: Database server running PostgreSQL.

```
vault kv put secret/eda-demo/app (Password rotation)
        -> file audit on vault.nostromo.io
        -> ssh tail -F /opt/vault/logs/audit.json
        -> ansible-rulebook (aap.nostromo.io)
        -> run update_passwords.yml
        -> ssh to rhel01 (Updates config.ini)
        -> ssh to rhel03 (Updates PostgreSQL appuser)
```

## Prerequisites

- SSH as `root@vault.nostromo.io` with a key (BatchMode).
- Vault root token and unseal key in `demo/.env` (not committed).
- The AAP host must be configured with SSH keys to connect to `rhel01` and `rhel03`.

## Setup Target Hosts

Before running the demo, ensure the target hosts (`rhel01`, `rhel03`) are provisioned:

```bash
cd demo
ansible-playbook -i inventory.yml playbooks/setup_target_hosts.yml
```

## Running the Demo

The EDA rulebook runs as a systemd user service (`vault-eda-demo`) under the `srvadmin` user on `aap.nostromo.io`.

### Terminal 1 — Watch EDA Logs on AAP

```bash
ssh srvadmin@aap.nostromo.io
export XDG_RUNTIME_DIR=/run/user/1000
podman logs -f vault-eda-demo
```

### Terminal 2 — Trigger Password Rotation (Local)

From your laptop, trigger a password rotation in Vault. The script generates a random 16-character password and saves it to Vault.

```bash
cd /home/nmartins/Development/AI-Assisted/vault-plugin
python3 demo/scripts/trigger_secret.py write
```

### 3. Verify Updates

Watch the `podman logs` in Terminal 1. You should see the event being received and the `update_passwords.yml` playbook being executed.

Verify the changes on the target systems:

* **rhel01**: `ssh root@rhel01.nostromo.io cat /etc/myapp/config.ini` (Check the new password)
* **rhel03**: The database password for `appuser` will be updated (use `psql` to verify login if desired).

Service control on AAP:

```bash
ssh srvadmin@aap.nostromo.io
export XDG_RUNTIME_DIR=/run/user/1000
systemctl --user restart vault-eda-demo
```
