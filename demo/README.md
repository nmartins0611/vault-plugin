# Vault + EDA Demo (vault.nostromo.io)

This demo reacts to secret writes on the homelab Vault at `http://vault.nostromo.io:8200` and automatically rotates passwords across an application server and a database.

That Vault is Community / OpenBao 2.0.4. The Events WebSocket API (`/v1/sys/events/subscribe/...`) is Enterprise-only. The demo therefore uses a **file audit device** on the Vault host and tails it over SSH into Event-Driven Ansible.

## Topology

* **`vault.nostromo.io`**: HashiCorp Vault (OpenBao) instance generating events via file audit.
* **`aap.nostromo.io`**: Ansible Automation Platform. The Controller job template updates the targets; an EDA rulebook activation launches that template.
* **`rhel01.nostromo.io`**: Mock application server that reads configuration from `/etc/myapp/config.ini`.
* **`rhel03.nostromo.io`**: Database server running PostgreSQL.

```
vault kv put secret/eda-demo/app (password rotation)
        -> file audit on vault.nostromo.io
        -> EDA activation (hashicorp.vault.vault_audit)
        -> job template "Vault rotate app and db passwords"
        -> rhel01 /etc/myapp/config.ini
        -> rhel03 PostgreSQL role appuser
```

## Prerequisites

- SSH as `root@vault.nostromo.io` with a key (BatchMode).
- Vault root token and unseal key in `demo/.env` (not committed).
- The AAP host must be able to SSH to `rhel01` and `rhel03` (OT Lab Credential).

## Setup Target Hosts

Before running the demo, ensure the target hosts (`rhel01`, `rhel03`) are provisioned:

```bash
cd demo
ansible-playbook -i inventory.yml playbooks/setup_target_hosts.yml
```

## Running the demo in AAP

Log in at **https://aap.nostromo.io/** as `admin` (installer inventory password).

| Object | Where in the UI |
| --- | --- |
| Project | Automation Execution → Projects → `Vault EDA Demo` |
| Job template | Automation Execution → Templates → `Vault rotate app and db passwords` |
| Inventory | Automation Execution → Inventories → `OT Lab Hosts` (`rhel01`, `rhel03`) |
| EDA project | Automation Decisions → Projects → `Vault EDA Demo` |
| Decision environment | Automation Decisions → Decision Environments → `Vault Audit Decision Environment` |
| Rulebook activation | Automation Decisions → Rulebook Activations → `Vault secret rotation` |

Open the `Vault secret rotation` activation and follow its logs. Controller jobs appear under **Jobs**.

### Trigger a rotation

From the Vault UI (`http://vault.nostromo.io:8200`) save a new version of `secret/eda-demo/app`, or from this repo:

```bash
python3 demo/scripts/trigger_secret.py write
```

### Verify

```bash
ssh root@rhel01.nostromo.io cat /etc/myapp/config.ini
```
