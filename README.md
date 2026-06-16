# HashiCorp Vault Event-Driven Ansible Plugin

An Event-Driven Ansible (EDA) plugin that subscribes to HashiCorp Vault's event notification system via WebSocket, enabling real-time automation based on Vault activity.

## Features

- **Real-time Event Streaming**: Subscribe to Vault events via WebSocket
- **Multiple Authentication Methods**: Support for direct tokens, token files, and AppRole
- **Automatic Reconnection**: Exponential backoff with configurable retry logic
- **Event Filtering**: Subscribe to specific event types or all events
- **Enterprise Support**: Vault Enterprise namespace support
- **Flexible SSL/TLS**: Configurable certificate verification and custom CA bundles
- **CloudEvents Format**: Processes Vault CloudEvents and transforms them for EDA

## Requirements

- **HashiCorp Vault Enterprise**: Version 1.16+ (or HCP Vault Dedicated). The events WebSocket API is not available in Community Edition.
- **Event-Driven Ansible**: ansible-rulebook CLI
- **Python**: 3.9+
- **Python Packages**:
  - `websockets>=12.0`
  - `aiohttp>=3.9.0`

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Build and Install the Collection

```bash
# Build the collection
ansible-galaxy collection build

# Install the collection
ansible-galaxy collection install hashicorp-vault-1.0.0.tar.gz
```

### 3. Verify Installation

```bash
ansible-galaxy collection list | grep hashicorp.vault
```

## Vault Configuration

### Events API

The Vault events API is available by default in Vault 1.16+. No separate enablement step is required.

### Required Permissions

The authentication token/role must have permissions to subscribe to events:

```hcl
# Allow subscribing to all events
path "sys/events/subscribe/*" {
  capabilities = ["read"]
}

# Or specific event types
path "sys/events/subscribe/kv-v2/*" {
  capabilities = ["read"]
}
```

## Authentication Methods

### 1. Direct Token Authentication

```yaml
sources:
  - hashicorp.vault.vault_events:
      vault_url: "https://vault.example.com:8200"
      vault_token: "{{ VAULT_TOKEN }}"
```

### 2. Token from File

```yaml
sources:
  - hashicorp.vault.vault_events:
      vault_url: "https://vault.example.com:8200"
      vault_token_path: "/var/run/secrets/vault-token"
```

### 3. AppRole Authentication

```yaml
sources:
  - hashicorp.vault.vault_events:
      vault_url: "https://vault.example.com:8200"
      approle_role_id: "{{ VAULT_ROLE_ID }}"
      approle_secret_id: "{{ VAULT_SECRET_ID }}"
```

## Configuration Parameters

### Required

| Parameter | Type | Description |
|-----------|------|-------------|
| `vault_url` | string | Vault server URL (e.g., `https://vault.example.com:8200`) |

### Authentication (one required)

| Parameter | Type | Description |
|-----------|------|-------------|
| `vault_token` | string | Direct Vault token |
| `vault_token_path` | string | Path to file containing token |
| `approle_role_id` | string | AppRole role ID (requires `approle_secret_id`) |
| `approle_secret_id` | string | AppRole secret ID (requires `approle_role_id`) |

### Optional

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `event_types` | list | `["*"]` | Event types to subscribe to |
| `vault_namespace` | string | - | Vault Enterprise namespace |
| `verify_ssl` | bool | `true` | Verify SSL certificates |
| `ca_cert_path` | string | - | Custom CA certificate path |
| `ping_interval` | int | `20` | WebSocket ping interval (seconds) |
| `ping_timeout` | int | `20` | WebSocket ping timeout (seconds) |
| `reconnect_enabled` | bool | `true` | Enable automatic reconnection |
| `reconnect_max_attempts` | int | `-1` | Max reconnection attempts (-1 = infinite) |
| `reconnect_initial_delay` | float | `1.0` | Initial reconnection delay (seconds) |
| `reconnect_max_delay` | float | `60.0` | Maximum reconnection delay (seconds) |
| `reconnect_backoff_multiplier` | float | `2.0` | Backoff multiplier for exponential backoff |

## Event Types

Subscribe to specific event types or use wildcards:

| Pattern | Description |
|---------|-------------|
| `*` | All events (default) |
| `kv-v2/*` | All KV-v2 events |
| `kv-v2/data-write` | KV-v2 write events only |
| `kv-v2/data-delete` | KV-v2 delete events only |
| `audit/*` | All audit events |

## Event Structure

Events are delivered in a transformed format optimized for EDA:

```yaml
vault:
  event_type: "kv-v2/data-write"
  metadata:
    path: "secret/data/myapp/config"
    operation: "write"
  plugin_info:
    mount_path: "secret/"
    plugin: "kv"
cloudevents:
  id: "event-uuid"
  source: "vault://cluster-id"
  time: "2025-06-12T15:19:49Z"
```

## Usage Examples

### Basic Usage

```yaml
---
- name: Handle Vault Events
  hosts: all
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
          msg: "Event: {{ event.vault.event_type }} at {{ event.vault.metadata.path }}"
```

### Filtering Specific Events

```yaml
---
- name: Monitor Secret Changes
  hosts: all
  sources:
    - hashicorp.vault.vault_events:
        vault_url: "https://vault.example.com:8200"
        vault_token: "{{ vault_token }}"
        event_types:
          - "kv-v2/data-write"
          - "kv-v2/data-delete"

  rules:
    - name: Alert on production secret changes
      condition: event.vault.metadata.path is match("secret/data/prod/.*")
      action:
        run_playbook:
          name: alert_secret_change.yml
```

### With AppRole and Custom Reconnection

```yaml
---
- name: Vault Events with AppRole
  hosts: all
  sources:
    - hashicorp.vault.vault_events:
        vault_url: "https://vault.example.com:8200"
        approle_role_id: "{{ VAULT_ROLE_ID }}"
        approle_secret_id: "{{ VAULT_SECRET_ID }}"
        event_types:
          - "kv-v2/*"
        reconnect_max_attempts: 10
        reconnect_initial_delay: 2
        reconnect_max_delay: 120

  rules:
    - name: Process KV writes
      condition: event.vault.event_type == "kv-v2/data-write"
      action:
        debug:
          msg: "Secret written: {{ event.vault.metadata.path }}"
```

### With Custom CA Certificate

```yaml
---
- name: Vault Events with Custom CA
  hosts: all
  sources:
    - hashicorp.vault.vault_events:
        vault_url: "https://vault.example.com:8200"
        vault_token: "{{ vault_token }}"
        verify_ssl: true
        ca_cert_path: "/etc/ssl/certs/vault-ca.crt"
        event_types:
          - "*"

  rules:
    - name: Log events
      condition: event.vault is defined
      action:
        debug:
          msg: "{{ event }}"
```

## Running the Plugin

### Start ansible-rulebook

```bash
# With environment variables
export VAULT_TOKEN="your-token"
ansible-rulebook -i inventory.yml --rulebook basic_rulebook.yml

# With AppRole
export VAULT_ROLE_ID="your-role-id"
export VAULT_SECRET_ID="your-secret-id"
ansible-rulebook -i inventory.yml --rulebook approle_rulebook.yml

# With verbose logging
ansible-rulebook -i inventory.yml --rulebook basic_rulebook.yml -v
```

### Testing Event Generation

Trigger events in Vault to test the plugin:

```bash
# Write a secret (triggers kv-v2/data-write)
vault kv put secret/test key=value

# Delete a secret (triggers kv-v2/data-delete)
vault kv delete secret/test

# Update metadata (triggers kv-v2/metadata-write)
vault kv metadata put -max-versions=5 secret/test
```

## Troubleshooting

### Connection Issues

**Problem**: Cannot connect to Vault WebSocket

**Solutions**:
- Verify Vault URL is correct and includes protocol and port
- Check that Vault version is 1.16+ (`vault status`)
- Verify network connectivity and firewall rules
- Check SSL/TLS configuration if using HTTPS

### Authentication Errors

**Problem**: Authentication fails

**Solutions**:
- Verify token has not expired
- Check token has `sys/events/subscribe/*` permissions
- For AppRole, verify role_id and secret_id are correct
- Check namespace is correct (if using Vault Enterprise)

### No Events Received

**Problem**: Connected but no events appear

**Solutions**:
- Verify event_types pattern matches expected events
- Check Vault activity is actually generating events
- Increase logging verbosity: `ansible-rulebook -vvv`
- Test with `event_types: ["*"]` to see all events

### Reconnection Issues

**Problem**: Plugin doesn't reconnect after disconnect

**Solutions**:
- Verify `reconnect_enabled: true`
- Check `reconnect_max_attempts` is not set too low
- Review logs for error messages during reconnection
- Verify authentication credentials are still valid

## Architecture

### Components

1. **VaultAuthenticator**: Handles multiple authentication methods
2. **VaultWebSocketClient**: Manages WebSocket connections to Vault
3. **ReconnectionManager**: Implements exponential backoff reconnection logic
4. **EventProcessor**: Transforms CloudEvents to EDA-friendly format
5. **main()**: Orchestrates all components and event processing

### Event Flow

```
Vault Events API
      ↓ (WebSocket)
VaultWebSocketClient
      ↓
EventProcessor
      ↓
asyncio.Queue
      ↓
EDA Rulebook Rules
      ↓
Ansible Actions
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

Apache License 2.0

## Support

- **Issues**: https://github.com/your-org/vault-plugin/issues
- **Documentation**: https://github.com/your-org/vault-plugin
- **Vault Events API**: https://developer.hashicorp.com/vault/docs/concepts/events

## Future Enhancements

Planned features for future releases:

- Kubernetes authentication method
- AWS IAM authentication method
- Event batching for high-volume scenarios
- Advanced event filtering based on metadata
- Metrics and monitoring hooks
- Multiple concurrent event type subscriptions
- Event replay from specific timestamp
