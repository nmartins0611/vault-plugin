# Testing Guide

This guide helps you test the HashiCorp Vault EDA plugin in your environment.

## Prerequisites

1. **HashiCorp Vault 1.16+** running and accessible
2. **Python 3.9+** installed
3. **ansible-rulebook** installed
4. Vault events API enabled

## Setup Test Environment

### 1. Install Dependencies

```bash
cd vault-plugin
pip install -r requirements.txt
```

### 2. Build and Install Collection

```bash
# Build the collection
ansible-galaxy collection build

# Install locally
ansible-galaxy collection install hashicorp-vault-1.0.0.tar.gz --force
```

### 3. Verify Installation

```bash
# Check collection is installed
ansible-galaxy collection list | grep hashicorp.vault

# Verify plugin file exists
python -c "import ansible_collections.hashicorp.vault.extensions.eda.plugins.event_source.vault_events as v; print('Plugin loaded successfully')"
```

## Configure Vault

### Set Environment

```bash
export VAULT_ADDR="https://your-vault-server:8200"
export VAULT_TOKEN="your-root-token"
```

The events API is available by default in Vault 1.16+ — no separate enablement step is required.

### Create Test Policy

Create a policy that allows event subscription:

```bash
vault policy write eda-events - <<EOF
# Allow subscribing to events
path "sys/events/subscribe/*" {
  capabilities = ["read"]
}

# Allow KV operations for testing
path "secret/data/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
EOF
```

### Create Test Token

```bash
# Create token with the policy
vault token create -policy=eda-events -ttl=1h
# Save the token for testing
export VAULT_TEST_TOKEN="<token-from-above>"
```

### (Optional) Setup AppRole

```bash
# Enable AppRole
vault auth enable approle

# Create role with policy
vault write auth/approle/role/eda-test \
    token_policies="eda-events" \
    token_ttl=1h \
    token_max_ttl=4h

# Get role ID
vault read auth/approle/role/eda-test/role-id
export VAULT_ROLE_ID="<role-id>"

# Generate secret ID
vault write -f auth/approle/role/eda-test/secret-id
export VAULT_SECRET_ID="<secret-id>"
```

## Test Scenarios

### Test 1: Basic Connection Test

Create `test_inventory.yml`:

```yaml
---
all:
  hosts:
    localhost:
      ansible_connection: local
```

Create `test_basic.yml`:

```yaml
---
- name: Test Vault Events Connection
  hosts: localhost
  sources:
    - hashicorp.vault.vault_events:
        vault_url: "{{ VAULT_ADDR }}"
        vault_token: "{{ VAULT_TEST_TOKEN }}"
        event_types:
          - "*"
        reconnect_max_attempts: 3

  rules:
    - name: Log all events
      condition: event.vault is defined
      action:
        debug:
          msg: "Received: {{ event.vault.event_type }}"
```

Run the test:

```bash
ansible-rulebook \
  -i test_inventory.yml \
  --rulebook test_basic.yml \
  -v
```

In another terminal, trigger an event:

```bash
vault kv put secret/test message="Hello from test"
```

You should see the event logged in the ansible-rulebook output.

### Test 2: AppRole Authentication

```bash
ansible-rulebook \
  -i test_inventory.yml \
  --rulebook docs/examples/approle_rulebook.yml \
  -v
```

### Test 3: Event Type Filtering

Create `test_kv_only.yml`:

```yaml
---
- name: Test KV Events Only
  hosts: localhost
  sources:
    - hashicorp.vault.vault_events:
        vault_url: "{{ VAULT_ADDR }}"
        vault_token: "{{ VAULT_TEST_TOKEN }}"
        event_types:
          - "kv-v2/data-write"
          - "kv-v2/data-delete"

  rules:
    - name: Count KV writes
      condition: event.vault.event_type == "kv-v2/data-write"
      action:
        debug:
          msg: "KV Write: {{ event.vault.metadata.path }}"

    - name: Count KV deletes
      condition: event.vault.event_type == "kv-v2/data-delete"
      action:
        debug:
          msg: "KV Delete: {{ event.vault.metadata.path }}"
```

Run and test:

```bash
ansible-rulebook -i test_inventory.yml --rulebook test_kv_only.yml -v

# In another terminal
vault kv put secret/test1 key=value
vault kv delete secret/test1
```

### Test 4: Reconnection Logic

This test verifies the plugin reconnects after connection loss:

```bash
# Start the rulebook
ansible-rulebook -i test_inventory.yml --rulebook test_basic.yml -v

# Restart the Vault container to simulate connection loss
podman restart <vault-container>

# Wait ~30 seconds for the plugin to detect the disconnect and reconnect

# Verify the plugin reconnects and continues receiving events
vault kv put secret/test-reconnect value=123
```

### Test 5: SSL/TLS Configuration

Create `test_ssl.yml`:

```yaml
---
- name: Test Custom CA Certificate
  hosts: localhost
  sources:
    - hashicorp.vault.vault_events:
        vault_url: "{{ VAULT_ADDR }}"
        vault_token: "{{ VAULT_TEST_TOKEN }}"
        event_types:
          - "*"
        verify_ssl: true
        ca_cert_path: "/path/to/vault-ca.crt"  # Update with your CA path

  rules:
    - name: Log events
      condition: event.vault is defined
      action:
        debug:
          msg: "{{ event }}"
```

### Test 6: Performance Test

Generate multiple events to test performance:

```bash
# Start rulebook
ansible-rulebook -i test_inventory.yml --rulebook test_basic.yml

# In another terminal, generate 100 events
for i in {1..100}; do
  vault kv put secret/perf-test-$i value=$i
  echo "Created secret $i"
done
```

Monitor the rulebook output to verify all events are received.

## Validation Checklist

- [ ] Plugin connects to Vault successfully
- [ ] Events are received and logged
- [ ] Token authentication works
- [ ] AppRole authentication works (if configured)
- [ ] Event filtering works correctly
- [ ] Plugin reconnects after connection loss
- [ ] SSL/TLS verification works (if applicable)
- [ ] Multiple event types can be subscribed
- [ ] CloudEvents are properly transformed
- [ ] No memory leaks during extended operation

## Troubleshooting

### Enable Debug Logging

```bash
# Maximum verbosity
ansible-rulebook -i test_inventory.yml --rulebook test_basic.yml -vvvv
```

### Check Plugin Loading

```python
# Test if plugin can be imported
python3 << EOF
import sys
sys.path.insert(0, './extensions/eda/plugins/event_source')
import vault_events
print("Plugin loaded successfully")
print(f"Module: {vault_events.__file__}")
print(f"Main function: {vault_events.main}")
EOF
```

### Verify Vault Events API

```bash
# Check Vault version is 1.16+ (events API is available by default)
vault status
```

### Test WebSocket Connection Manually

```python
import asyncio
import websockets
import ssl

async def test_ws():
    vault_url = "wss://your-vault:8200/v1/sys/events/subscribe/*?json=true"
    headers = {"X-Vault-Token": "your-token"}

    ssl_context = ssl.create_default_context()
    # ssl_context.check_hostname = False
    # ssl_context.verify_mode = ssl.CERT_NONE

    async with websockets.connect(vault_url, extra_headers=headers, ssl=ssl_context) as ws:
        print("Connected!")
        async for message in ws:
            print(f"Received: {message}")
            break

asyncio.run(test_ws())
```

## Common Issues

### Issue: "Failed to connect to Vault WebSocket"

**Solutions:**
- Verify VAULT_ADDR is correct (include https:// and port)
- Check firewall allows WebSocket connections
- Verify Vault is running and accessible
- Check SSL/TLS configuration

### Issue: "Authentication failed"

**Solutions:**
- Verify token is valid: `vault token lookup`
- Check token has required permissions
- For AppRole, verify role_id and secret_id are correct

### Issue: "No events received"

**Solutions:**
- Verify Vault version is 1.16+ (`vault status`)
- Check event_types pattern is correct
- Try subscribing to "*" to see all events
- Generate test events: `vault kv put secret/test key=value`

### Issue: Plugin doesn't reconnect

**Solutions:**
- Check `reconnect_enabled: true` in rulebook
- Verify `reconnect_max_attempts` is not too low
- Review logs for specific error messages
- Check token hasn't expired (tokens expire on reconnect)

## Next Steps

After successful testing:

1. **Production Deployment**: Review security settings (SSL, token management)
2. **Monitoring**: Set up logging and monitoring for the rulebook
3. **Automation**: Create playbooks for common event scenarios
4. **Integration**: Integrate with your existing automation workflows

## References

- [Vault Events API Documentation](https://developer.hashicorp.com/vault/docs/concepts/events)
- [Event-Driven Ansible Documentation](https://ansible.readthedocs.io/projects/rulebook/)
- [WebSocket Protocol](https://websockets.readthedocs.io/)
