# Quick Start Guide

Get started with the HashiCorp Vault EDA plugin in 5 minutes.

## Prerequisites

- HashiCorp Vault 1.16+ running at `https://vault.example.com:8200`
- Python 3.9+
- ansible-rulebook installed
- Vault token with event subscription permissions

## Step 1: Install

```bash
# Clone or download the plugin
cd vault-plugin

# Install Python dependencies
pip install -r requirements.txt

# Build and install the collection
ansible-galaxy collection build
ansible-galaxy collection install hashicorp-vault-1.0.0.tar.gz --force
```

## Step 2: Configure Vault

```bash
# Set Vault address
export VAULT_ADDR="https://vault.example.com:8200"
export VAULT_TOKEN="your-vault-token"
```

The events API is available by default in Vault 1.16+ — no separate enablement step is required.

## Step 3: Create a Simple Rulebook

Create `my-first-rulebook.yml`:

```yaml
---
- name: My First Vault Events
  hosts: localhost
  sources:
    - hashicorp.vault.vault_events:
        vault_url: "https://vault.example.com:8200"
        vault_token: "{{ VAULT_TOKEN }}"
        event_types:
          - "*"

  rules:
    - name: Log all events
      condition: event.vault is defined
      action:
        debug:
          msg: |
            Event Type: {{ event.vault.event_type }}
            Path: {{ event.vault.metadata.path | default('N/A') }}
```

Create `inventory.yml`:

```yaml
---
all:
  hosts:
    localhost:
      ansible_connection: local
```

## Step 4: Run the Rulebook

```bash
ansible-rulebook -i inventory.yml --rulebook my-first-rulebook.yml
```

You should see output like:

```
2025-03-13 10:00:00,000 - ansible_rulebook.app - INFO - Starting sources
2025-03-13 10:00:00,100 - ansible_rulebook.engine - INFO - Starting Vault events plugin for: https://vault.example.com:8200
2025-03-13 10:00:00,200 - ansible_rulebook.engine - INFO - Connected to Vault events
2025-03-13 10:00:00,300 - ansible_rulebook.engine - INFO - Listening for Vault events...
```

## Step 5: Generate Test Events

In another terminal:

```bash
# Write a secret (triggers kv-v2/data-write event)
vault kv put secret/test message="Hello EDA"

# Delete the secret (triggers kv-v2/data-delete event)
vault kv delete secret/test
```

You should see the events appear in the ansible-rulebook output:

```
Event Type: kv-v2/data-write
Path: secret/data/test

Event Type: kv-v2/data-delete
Path: secret/data/test
```

## Next Steps

### Try More Examples

```bash
# Basic example
ansible-rulebook -i docs/examples/inventory.yml --rulebook docs/examples/basic_rulebook.yml

# AppRole example (set VAULT_ROLE_ID and VAULT_SECRET_ID first)
ansible-rulebook -i docs/examples/inventory.yml --rulebook docs/examples/approle_rulebook.yml
```

### Create Custom Rules

Modify `my-first-rulebook.yml` to add specific actions:

```yaml
rules:
  # Alert on production secret changes
  - name: Production alert
    condition: >
      event.vault.event_type == "kv-v2/data-write" and
      event.vault.metadata.path is match("secret/data/prod/.*")
    action:
      run_playbook:
        name: alert_team.yml
        extra_vars:
          secret_path: "{{ event.vault.metadata.path }}"

  # Log audit events
  - name: Audit logging
    condition: event.vault.event_type is match("audit/.*")
    action:
      debug:
        msg: "Audit event detected"
```

### Explore Event Types

Subscribe to specific event patterns:

```yaml
event_types:
  - "kv-v2/*"          # All KV events
  - "audit/*"          # All audit events
  - "kv-v2/data-write" # Only write events
```

## Common Commands

```bash
# Build collection
ansible-galaxy collection build

# Install collection (force overwrite)
ansible-galaxy collection install hashicorp-vault-1.0.0.tar.gz --force

# List installed collections
ansible-galaxy collection list | grep vault

# Run with verbose output
ansible-rulebook -i inventory.yml --rulebook rulebook.yml -v

# Run with maximum verbosity (debug)
ansible-rulebook -i inventory.yml --rulebook rulebook.yml -vvvv
```

## Troubleshooting

### Can't connect to Vault

```bash
# Check Vault is accessible
curl -k $VAULT_ADDR/v1/sys/health

# Verify Vault version is 1.16+
vault status
```

### No events received

```bash
# Subscribe to all events
event_types: ["*"]

# Check token permissions
vault token lookup

# Generate test event
vault kv put secret/test key=value
```

### Authentication fails

```bash
# Verify token is valid
vault token lookup $VAULT_TOKEN

# For AppRole, test login
vault write auth/approle/login role_id=$ROLE_ID secret_id=$SECRET_ID
```

## Learn More

- [Full Documentation](../README.md)
- [Testing Guide](TESTING.md)
- [Example Rulebooks](examples/)
- [Vault Events API](https://developer.hashicorp.com/vault/docs/concepts/events)

## Get Help

- GitHub Issues: https://github.com/your-org/vault-plugin/issues
- Documentation: https://github.com/your-org/vault-plugin
