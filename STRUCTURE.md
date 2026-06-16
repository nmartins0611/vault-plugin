# Project Structure

This document describes the organization of the HashiCorp Vault EDA plugin project.

## Directory Tree

```
vault-plugin/
├── build.sh                          # Build and installation script
├── galaxy.yml                        # Ansible collection metadata
├── LICENSE                           # Apache 2.0 license
├── MANIFEST.in                       # Package manifest for distribution
├── README.md                         # Main documentation
├── requirements.txt                  # Python dependencies
├── STRUCTURE.md                      # This file
├── .gitignore                        # Git ignore rules
│
├── extensions/                       # EDA extensions
│   └── eda/
│       └── plugins/
│           └── event_source/
│               └── vault_events.py   # Main plugin implementation (CRITICAL)
│
└── docs/                            # Documentation and examples
    ├── QUICKSTART.md                # Quick start guide
    ├── TESTING.md                   # Testing and validation guide
    └── examples/
        ├── inventory.yml            # Example inventory file
        ├── basic_rulebook.yml       # Basic usage example
        └── approle_rulebook.yml     # AppRole authentication example
```

## Core Files

### Collection Configuration

- **`galaxy.yml`**: Ansible Galaxy collection metadata
  - Namespace: `hashicorp`
  - Collection name: `vault`
  - Version: `1.0.0`
  - Defines collection properties, dependencies, and metadata

- **`requirements.txt`**: Python package dependencies
  - `websockets>=12.0`: WebSocket client library
  - `aiohttp>=3.9.0`: Async HTTP client for Vault API

### Main Plugin

- **`extensions/eda/plugins/event_source/vault_events.py`**: The main plugin implementation (~600 lines)
  - `async def main(queue, args)`: EDA entry point
  - `VaultAuthenticator`: Handles authentication (token, file, AppRole)
  - `VaultWebSocketClient`: Manages WebSocket connections
  - `ReconnectionManager`: Implements exponential backoff reconnection
  - `EventProcessor`: Transforms CloudEvents to EDA format

### Documentation

- **`README.md`**: Comprehensive documentation
  - Features and requirements
  - Installation instructions
  - Authentication methods
  - Configuration parameters
  - Usage examples
  - Troubleshooting guide

- **`docs/QUICKSTART.md`**: 5-minute quick start guide
  - Minimal setup instructions
  - Simple examples
  - Common commands

- **`docs/TESTING.md`**: Testing and validation guide
  - Test environment setup
  - Multiple test scenarios
  - Validation checklist
  - Troubleshooting steps

### Examples

- **`docs/examples/inventory.yml`**: Basic inventory file for localhost
- **`docs/examples/basic_rulebook.yml`**: Simple rulebook with token auth
- **`docs/examples/approle_rulebook.yml`**: Advanced rulebook with AppRole auth

### Build Tools

- **`build.sh`**: Automated build and installation script
  - `./build.sh`: Build and install collection
  - `./build.sh --clean`: Clean build artifacts
  - `./build.sh --test`: Build, install, and run tests

### Supporting Files

- **`LICENSE`**: Apache 2.0 license
- **`.gitignore`**: Git ignore patterns
- **`MANIFEST.in`**: Python package manifest

## Plugin Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    EDA Rulebook Engine                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                   main(queue, args)                          │
│  - Entry point called by ansible-rulebook                   │
│  - Orchestrates all components                              │
│  - Manages main event loop                                  │
└────────────┬────────────────────────────────────────────────┘
             │
             ├──→ VaultAuthenticator
             │    - Token authentication
             │    - Token from file
             │    - AppRole login
             │
             ├──→ VaultWebSocketClient
             │    - WebSocket connection management
             │    - SSL/TLS configuration
             │    - Keepalive (ping/pong)
             │
             ├──→ ReconnectionManager
             │    - Exponential backoff
             │    - Jitter calculation
             │    - Attempt tracking
             │
             └──→ EventProcessor
                  - CloudEvents parsing
                  - Event transformation
                  - EDA format conversion
```

### Event Flow

```
Vault Events API
      │ (WebSocket)
      ↓
VaultWebSocketClient
      │ (Raw CloudEvent JSON)
      ↓
EventProcessor
      │ (Transformed event dict)
      ↓
asyncio.Queue
      │
      ↓
EDA Rules Engine
      │
      ↓
Ansible Actions
(debug, run_playbook, etc.)
```

### Authentication Priority

```
1. vault_token (direct)
   ↓ (if not provided)
2. vault_token_path (file)
   ↓ (if not provided)
3. approle_role_id + approle_secret_id
   ↓ (if none provided)
4. ValueError
```

## Development Workflow

### 1. Modify Plugin

Edit `extensions/eda/plugins/event_source/vault_events.py`

### 2. Build Collection

```bash
./build.sh
```

### 3. Test Locally

```bash
ansible-rulebook -i docs/examples/inventory.yml \
  --rulebook docs/examples/basic_rulebook.yml
```

### 4. Run Tests

```bash
./build.sh --test
```

## Plugin Configuration

### Required Parameters

- `vault_url`: Vault server URL

### Authentication (choose one)

- `vault_token`: Direct token
- `vault_token_path`: Token file path
- `approle_role_id` + `approle_secret_id`: AppRole credentials

### Optional Parameters

- `event_types`: List of event patterns (default: `["*"]`)
- `vault_namespace`: Vault Enterprise namespace
- `verify_ssl`: SSL verification (default: `true`)
- `ca_cert_path`: Custom CA certificate
- `ping_interval`: WebSocket ping interval (default: `20`)
- `ping_timeout`: WebSocket ping timeout (default: `20`)
- `reconnect_enabled`: Enable reconnection (default: `true`)
- `reconnect_max_attempts`: Max reconnection attempts (default: `-1`)
- `reconnect_initial_delay`: Initial delay (default: `1.0`)
- `reconnect_max_delay`: Max delay (default: `60.0`)
- `reconnect_backoff_multiplier`: Backoff multiplier (default: `2.0`)

## Event Structure

### Input (Vault CloudEvents)

```json
{
  "id": "event-uuid",
  "source": "vault://cluster",
  "specversion": "1.0",
  "type": "*",
  "data": {
    "event_type": "kv-v2/data-write",
    "metadata": {
      "path": "secret/data/foo",
      "operation": "write"
    },
    "plugin_info": {
      "mount_path": "secret/",
      "plugin": "kv"
    }
  },
  "time": "2025-06-12T15:19:49Z"
}
```

### Output (EDA Format)

```python
{
  "vault": {
    "event_type": "kv-v2/data-write",
    "metadata": {
      "path": "secret/data/foo",
      "operation": "write"
    },
    "plugin_info": {
      "mount_path": "secret/",
      "plugin": "kv"
    }
  },
  "cloudevents": {
    "id": "event-uuid",
    "source": "vault://cluster",
    "time": "2025-06-12T15:19:49Z"
  }
}
```

## File Sizes

Approximate file sizes:

- `vault_events.py`: ~600 lines, ~25 KB
- `README.md`: ~400 lines, ~20 KB
- `TESTING.md`: ~400 lines, ~15 KB
- `galaxy.yml`: ~30 lines, ~1 KB
- `requirements.txt`: ~5 lines, ~200 bytes

Total project: ~1500 lines of code and documentation

## Version History

- **v1.0.0** (2025-03-13): Initial release
  - Token, file, and AppRole authentication
  - WebSocket event streaming
  - Automatic reconnection with exponential backoff
  - CloudEvents transformation
  - SSL/TLS support
  - Vault Enterprise namespace support

## Future Enhancements

Planned for future versions:

- v1.1.0: Kubernetes authentication
- v1.2.0: AWS IAM authentication
- v1.3.0: Event batching
- v1.4.0: Advanced filtering
- v1.5.0: Metrics and monitoring

## References

- [Ansible Galaxy](https://galaxy.ansible.com/)
- [Event-Driven Ansible](https://ansible.readthedocs.io/projects/rulebook/)
- [Vault Events API](https://developer.hashicorp.com/vault/docs/concepts/events)
- [CloudEvents Spec](https://cloudevents.io/)
