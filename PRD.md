# Product Requirements Document: HashiCorp Vault EDA Event Source Plugin

**Collection:** `hashicorp.vault`
**Version:** 1.0.0
**License:** Apache 2.0
**Last Updated:** 2026-05-26

---

## 1. Problem Statement

Organizations using HashiCorp Vault for secrets management lack a native way to trigger automated responses when Vault activity occurs. Today, teams either poll Vault's API on a schedule (introducing latency, unnecessary load, and missed events) or manually wire custom scripts to Vault's audit log (fragile, unscalable, no standard integration path).

Vault 1.16+ introduced a WebSocket-based Events API that streams activity in real time, but there is no packaged integration between this API and Ansible's event-driven automation framework (EDA). Security and operations teams want to react instantly to secrets writes, deletions, policy changes, and audit events without building and maintaining bespoke glue code.

## 2. Target Users

| Persona | Context |
|---------|---------|
| **Platform engineers** | Manage Vault infrastructure and need automated incident response when secrets are changed or deleted |
| **Security operators** | Monitor Vault audit trails and require real-time alerting for suspicious activity or policy violations |
| **DevOps / SRE teams** | Maintain application configuration in Vault and need to propagate secret rotations to dependent services |
| **Ansible automation developers** | Build EDA rulebooks and need a reliable, well-documented Vault event source that works out of the box |

## 3. Product Overview

An Ansible Galaxy collection (`hashicorp.vault`) providing a single EDA event source plugin (`vault_events`) that:

- Maintains a persistent WebSocket connection to Vault's Events API
- Streams real-time CloudEvents into the `ansible-rulebook` rules engine
- Supports multiple authentication methods for enterprise environments
- Handles connection failures with automatic reconnection and exponential backoff
- Transforms Vault's CloudEvents wire format into a clean, rule-friendly structure

The plugin acts as the bridge between "something happened in Vault" and "Ansible does something about it."

## 4. Goals and Success Criteria

### Goals

1. Provide a zero-custom-code path from Vault events to Ansible automation
2. Support production-grade deployment patterns (AppRole auth, TLS, namespaces, resilient connections)
3. Deliver an event format that is natural to write EDA rules against
4. Keep the plugin small, focused, and easy to audit (single-file implementation)

### Success Criteria

| Metric | Target |
|--------|--------|
| Time from Vault event to EDA rule evaluation | < 1 second (WebSocket latency only) |
| Reconnection after transient network failure | Automatic, no operator intervention |
| Authentication method coverage | Token, token file, AppRole at GA; K8s and AWS IAM post-GA |
| Installation to first event received | < 5 minutes with quickstart guide |
| Plugin file count | 1 Python file (maintainability) |

## 5. Requirements

### 5.1 Functional Requirements

#### FR-1: Real-Time Event Streaming

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-1.1 | Connect to Vault's `/v1/sys/events/subscribe/{event_type}` WebSocket endpoint | Must | Implemented |
| FR-1.2 | Subscribe to a configurable event type pattern (e.g., `*`, `kv-v2/*`, `audit/*`) | Must | Implemented |
| FR-1.3 | Support multiple concurrent event type subscriptions in a single plugin instance | Should | Not implemented (subscribes to first type only) |
| FR-1.4 | Maintain a long-lived WebSocket connection with configurable ping/pong keepalive | Must | Implemented |
| FR-1.5 | Yield each event to the EDA rules engine queue as it arrives | Must | Implemented |

#### FR-2: Authentication

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-2.1 | Authenticate with a direct Vault token (`vault_token`) | Must | Implemented |
| FR-2.2 | Read a Vault token from a file path (`vault_token_path`) | Must | Implemented |
| FR-2.3 | Authenticate via AppRole (`approle_role_id` + `approle_secret_id`) | Must | Implemented |
| FR-2.4 | Enforce a clear priority order: direct token > token file > AppRole | Must | Implemented |
| FR-2.5 | Raise an explicit error if no valid authentication method is provided | Must | Implemented |
| FR-2.6 | Re-authenticate on reconnection (token may have been refreshed on disk) | Should | Implemented |
| FR-2.7 | Authenticate via Kubernetes service account | Could | Planned (v1.1.0) |
| FR-2.8 | Authenticate via AWS IAM role | Could | Planned (v1.2.0) |

#### FR-3: Connection Resilience

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-3.1 | Automatically reconnect on connection loss when `reconnect_enabled` is true | Must | Implemented |
| FR-3.2 | Use exponential backoff with configurable initial delay, max delay, and multiplier | Must | Implemented |
| FR-3.3 | Add random jitter (±25%) to backoff delay to avoid thundering herd | Must | Implemented |
| FR-3.4 | Support infinite retry (`reconnect_max_attempts: -1`) and capped retry modes | Must | Implemented |
| FR-3.5 | Reset backoff counter after a successful connection | Must | Implemented |
| FR-3.6 | Log reconnection attempts with delay and attempt number | Must | Implemented |

#### FR-4: Event Processing

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-4.1 | Parse incoming JSON CloudEvents from the Vault wire format | Must | Implemented |
| FR-4.2 | Transform events into a two-section structure: `vault` (business data) and `cloudevents` (envelope metadata) | Must | Implemented |
| FR-4.3 | Handle both Vault 1.x and 2.0+ metadata nesting (`data.metadata` vs. `data.event.metadata`) | Must | Implemented |
| FR-4.4 | Log and skip malformed events without crashing the plugin | Must | Implemented |
| FR-4.5 | Expose `event_type`, `metadata.path`, `metadata.operation`, and `plugin_info` in the transformed output | Must | Implemented |

#### FR-5: TLS and Network Security

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-5.1 | Default to SSL certificate verification enabled | Must | Implemented |
| FR-5.2 | Allow disabling SSL verification for development (`verify_ssl: false`) | Must | Implemented |
| FR-5.3 | Support a custom CA certificate bundle (`ca_cert_path`) | Must | Implemented |
| FR-5.4 | Derive WebSocket scheme (`wss`/`ws`) from the Vault URL scheme (`https`/`http`) | Must | Implemented |

#### FR-6: Vault Enterprise Support

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-6.1 | Pass `X-Vault-Namespace` header for namespace-scoped connections | Must | Implemented |
| FR-6.2 | Apply namespace header to both AppRole login requests and WebSocket connections | Must | Implemented |

### 5.2 Non-Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| NFR-1 | Compatible with Python 3.9+ | Must | Met |
| NFR-2 | Compatible with HashiCorp Vault 1.16+ and HCP Vault Dedicated | Must | Met |
| NFR-3 | Packaged as a standard Ansible Galaxy collection installable via `ansible-galaxy` | Must | Met |
| NFR-4 | Fully async implementation (no blocking calls on the event loop) | Must | Met |
| NFR-5 | External dependencies limited to `websockets` and `aiohttp` | Must | Met |
| NFR-6 | Single-file plugin for ease of auditing and contribution | Should | Met |
| NFR-7 | Structured logging throughout all components | Must | Met |
| NFR-8 | Full Ansible plugin documentation block (`DOCUMENTATION`, `EXAMPLES`, `NOTES`) | Must | Met |

## 6. Architecture

### Component Model

```
┌──────────────────────────────────────────────────────────┐
│                  ansible-rulebook (EDA)                   │
│                                                          │
│  Calls main(queue, args) → receives events via queue     │
└────────────────────────┬─────────────────────────────────┘
                         │
          ┌──────────────┴──────────────┐
          │        main(queue, args)     │
          │   Orchestrator / Event Loop  │
          └──┬──────┬──────┬──────┬─────┘
             │      │      │      │
             ▼      │      │      │
  VaultAuthenticator│      │      │
  (token/file/AppRole)     │      │
             │      │      │      │
             ▼      ▼      │      │
     VaultWebSocketClient  │      │
     (connect, headers,    │      │
      SSL, keepalive)      │      │
                    │      │      │
                    │      ▼      │
                    │  ReconnectionManager
                    │  (backoff, jitter,  │
                    │   attempt tracking) │
                    │             │
                    ▼             │
               EventProcessor    │
               (CloudEvents →    │
                EDA format)      │
                    │             │
                    ▼             │
              asyncio.Queue ─────┘
                    │
                    ▼
             EDA Rules Engine
```

### Event Wire Format

**Input (Vault CloudEvents over WebSocket):**

```json
{
  "id": "abc-123",
  "source": "vault://cluster-xyz",
  "specversion": "1.0",
  "type": "*",
  "data": {
    "event_type": "kv-v2/data-write",
    "metadata": { "path": "secret/data/myapp/config", "operation": "write" },
    "plugin_info": { "mount_path": "secret/", "plugin": "kv" }
  },
  "time": "2025-06-12T15:19:49Z"
}
```

**Output (EDA-ready event dict):**

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
  id: "abc-123"
  source: "vault://cluster-xyz"
  time: "2025-06-12T15:19:49Z"
```

## 7. Configuration Reference

### Required

| Parameter | Type | Description |
|-----------|------|-------------|
| `vault_url` | `str` | Vault server URL including protocol and port |

### Authentication (exactly one method required)

| Parameter | Type | Description |
|-----------|------|-------------|
| `vault_token` | `str` | Direct Vault token |
| `vault_token_path` | `str` | Path to a file containing the Vault token |
| `approle_role_id` | `str` | AppRole role ID (must pair with `approle_secret_id`) |
| `approle_secret_id` | `str` | AppRole secret ID (must pair with `approle_role_id`) |

### Optional

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `event_types` | `list[str]` | `["*"]` | Event type patterns to subscribe to |
| `vault_namespace` | `str` | — | Vault Enterprise namespace |
| `verify_ssl` | `bool` | `true` | Whether to verify SSL certificates |
| `ca_cert_path` | `str` | — | Path to a custom CA certificate bundle |
| `ping_interval` | `int` | `20` | WebSocket ping interval in seconds |
| `ping_timeout` | `int` | `20` | WebSocket ping timeout in seconds |
| `reconnect_enabled` | `bool` | `true` | Enable automatic reconnection |
| `reconnect_max_attempts` | `int` | `-1` | Max reconnection attempts (-1 = infinite) |
| `reconnect_initial_delay` | `float` | `1.0` | Initial reconnection delay in seconds |
| `reconnect_max_delay` | `float` | `60.0` | Maximum reconnection delay in seconds |
| `reconnect_backoff_multiplier` | `float` | `2.0` | Backoff multiplier |

## 8. External Dependencies

| Dependency | Minimum Version | Purpose |
|------------|-----------------|---------|
| HashiCorp Vault | 1.16+ | Events API provider |
| Python | 3.9+ | Runtime |
| `ansible-rulebook` | — | EDA rules engine (host process) |
| `websockets` | 12.0+ | WebSocket client |
| `aiohttp` | 3.9.0+ | HTTP client for AppRole login |

## 9. Known Limitations (v1.0.0)

| # | Limitation | Impact | Workaround |
|---|-----------|--------|------------|
| 1 | Only the first entry in `event_types` is subscribed; additional types are silently ignored | Users who configure multiple event types get partial coverage | Use `*` wildcard, or run separate plugin instances per event type |
| 2 | No automated test suite | Regressions are caught late | Manual test scenarios documented in `docs/TESTING.md`; smoke test in `build.sh` |
| 3 | No CI/CD pipeline | No automated quality gate on changes | Run `./build.sh --test` locally before releasing |
| 4 | Repository URLs in `galaxy.yml` and README are placeholders (`your-org`) | Cannot be published to Ansible Galaxy as-is | Replace before first public release |
| 5 | Token renewal/rotation is not handled during an active session | Long-running connections may fail if the token expires | Use a long-TTL token or rely on reconnect (re-authenticates) |

## 10. Roadmap

### v1.0.0 — GA (current)

- Token, token file, and AppRole authentication
- WebSocket event streaming with CloudEvents transformation
- Automatic reconnection with exponential backoff + jitter
- SSL/TLS with custom CA support
- Vault Enterprise namespace support
- Documentation, examples, and build tooling

### v1.1.0 — Kubernetes Auth + Multi-Subscription

- Kubernetes service account authentication method
- Multiple concurrent event type subscriptions (resolves Known Limitation #1)

### v1.2.0 — AWS IAM Auth

- AWS IAM role-based authentication method

### v1.3.0 — High-Volume Improvements

- Event batching for high-throughput scenarios
- Advanced metadata-level filtering (reduce events before they reach rules)

### v1.4.0 — Observability

- Metrics and monitoring hooks (event counts, connection uptime, reconnection rate)
- Event replay from a specific timestamp

### Pre-GA Hardening (no version bump, before first public release)

- Replace placeholder repository URLs in `galaxy.yml` and `README.md`
- Add automated test suite (integration tests against a Vault dev server)
- Add CI/CD pipeline (GitHub Actions: lint, test, build, publish)
- Initialize git repository and push to target org

## 11. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Vault Events API is still evolving; wire format may change | Medium | High | Plugin already handles both Vault 1.x and 2.0+ metadata layouts; add integration tests against multiple Vault versions |
| WebSocket connections dropped by network proxies/load balancers | High | Medium | Configurable keepalive ping, automatic reconnection, exponential backoff |
| AppRole secret ID leak through logs | Low | Critical | Plugin never logs token or secret values; only auth method names are logged |
| Single event type subscription limits real-world usefulness | High | Medium | Documented as Known Limitation #1; scheduled for v1.1.0 |
| No automated tests means regressions ship undetected | Medium | High | Prioritize test suite and CI before first public release |

## 12. Out of Scope

The following are explicitly not part of this plugin:

- **Writing to Vault** — this is a read-only event source; it does not create, update, or delete Vault data
- **Event storage or replay** — the plugin streams events in real time and does not persist them (future replay support will use Vault's native replay API)
- **Vault secret retrieval** — use the existing `hashi_vault` lookup plugin for reading secrets; this plugin only processes event notifications
- **Multi-cluster aggregation** — each plugin instance connects to one Vault cluster; aggregate at the rulebook level by running multiple sources
- **Custom rule logic** — the plugin delivers events; rule conditions and actions are the domain of `ansible-rulebook`
