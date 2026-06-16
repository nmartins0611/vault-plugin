"""
DOCUMENTATION:
  name: vault_events
  short_description: Receive events from HashiCorp Vault via WebSocket
  description:
    - Connects to Vault's event notification system via WebSocket
    - Subscribes to audit events, KV writes, and more
    - Supports multiple authentication methods (token, AppRole, token file)
    - Automatically reconnects with exponential backoff
    - Transforms CloudEvents format to EDA-friendly structure
  version_added: "1.0.0"
  author:
    - HashiCorp Vault Plugin Team
  options:
    vault_url:
      description:
        - Vault server URL
        - Must include protocol (http:// or https://) and port
      required: true
      type: str
      example: "https://vault.example.com:8200"
    vault_token:
      description:
        - Vault authentication token
        - Takes precedence over token_path and AppRole
      required: false
      type: str
    vault_token_path:
      description:
        - Path to file containing Vault token
        - Used if vault_token is not provided
      required: false
      type: str
      example: "/var/run/secrets/vault-token"
    approle_role_id:
      description:
        - AppRole role ID for authentication
        - Must be used with approle_secret_id
      required: false
      type: str
    approle_secret_id:
      description:
        - AppRole secret ID for authentication
        - Must be used with approle_role_id
      required: false
      type: str
    vault_namespace:
      description:
        - Vault Enterprise namespace
        - Optional, only needed for namespaced Vault instances
      required: false
      type: str
      example: "admin/dev"
    event_types:
      description:
        - List of event types to subscribe to
        - Use "*" for all events, or specific patterns like "kv-v2/*", "audit/*"
      required: false
      type: list
      default: ["*"]
      example: ["kv-v2/*", "audit/*"]
    verify_ssl:
      description:
        - Verify SSL certificates
      required: false
      type: bool
      default: true
    ca_cert_path:
      description:
        - Path to custom CA certificate bundle
        - Only used when verify_ssl is true
      required: false
      type: str
      example: "/etc/ssl/certs/ca-bundle.crt"
    ping_interval:
      description:
        - WebSocket ping interval in seconds
      required: false
      type: int
      default: 20
    ping_timeout:
      description:
        - WebSocket ping timeout in seconds
      required: false
      type: int
      default: 20
    reconnect_enabled:
      description:
        - Enable automatic reconnection on connection loss
      required: false
      type: bool
      default: true
    reconnect_max_attempts:
      description:
        - Maximum number of reconnection attempts
        - Use -1 for infinite attempts
      required: false
      type: int
      default: -1
    reconnect_initial_delay:
      description:
        - Initial reconnection delay in seconds
      required: false
      type: float
      default: 1.0
    reconnect_max_delay:
      description:
        - Maximum reconnection delay in seconds
      required: false
      type: float
      default: 60.0
    reconnect_backoff_multiplier:
      description:
        - Backoff multiplier for exponential backoff
      required: false
      type: float
      default: 2.0

EXAMPLES:
  - name: Subscribe to all Vault events with token authentication
    vault_events:
      vault_url: "https://vault.example.com:8200"
      vault_token: "{{ VAULT_TOKEN }}"
      event_types:
        - "*"

  - name: Subscribe to KV events with AppRole authentication
    vault_events:
      vault_url: "https://vault.example.com:8200"
      approle_role_id: "{{ VAULT_ROLE_ID }}"
      approle_secret_id: "{{ VAULT_SECRET_ID }}"
      event_types:
        - "kv-v2/*"

  - name: Subscribe to audit events with token from file
    vault_events:
      vault_url: "https://vault.example.com:8200"
      vault_token_path: "/var/run/secrets/vault-token"
      event_types:
        - "audit/*"
      verify_ssl: true
      ca_cert_path: "/etc/ssl/certs/ca-bundle.crt"

  - name: Subscribe with custom reconnection settings
    vault_events:
      vault_url: "https://vault.example.com:8200"
      vault_token: "{{ vault_token }}"
      reconnect_max_attempts: 10
      reconnect_initial_delay: 2
      reconnect_max_delay: 120

NOTES:
  - Requires HashiCorp Vault 1.16+ with events API enabled
  - Events are delivered in CloudEvents format and transformed for EDA
  - Supports automatic reconnection with exponential backoff
  - Authentication methods priority: vault_token > vault_token_path > approle
"""

import asyncio
import json
import logging
import random
import ssl
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

try:
    import aiohttp
    import websockets
except ImportError as e:
    raise ImportError(
        f"Missing required dependency: {e}. "
        "Install with: pip install websockets aiohttp"
    )

# Configure logging
logger = logging.getLogger(__name__)


class VaultAuthenticator:
    """Handles authentication with HashiCorp Vault using multiple methods."""

    def __init__(self, vault_url: str, args: Dict[str, Any]):
        self.vault_url = vault_url.rstrip('/')
        self.args = args
        self.namespace = args.get('vault_namespace')
        self.verify_ssl = args.get('verify_ssl', True)
        self.ca_cert_path = args.get('ca_cert_path')

    async def authenticate(self) -> str:
        """
        Authenticate with Vault and return a valid token.

        Priority order:
        1. Direct token (vault_token)
        2. Token from file (vault_token_path)
        3. AppRole authentication (approle_role_id + approle_secret_id)

        Returns:
            str: Valid Vault token

        Raises:
            ValueError: If no valid authentication method is provided
        """
        # Priority 1: Direct token
        if 'vault_token' in self.args and self.args['vault_token']:
            logger.info("Using direct token authentication")
            return self.args['vault_token']

        # Priority 2: Token from file
        if 'vault_token_path' in self.args and self.args['vault_token_path']:
            logger.info(f"Reading token from file: {self.args['vault_token_path']}")
            return await self._read_token_from_file(self.args['vault_token_path'])

        # Priority 3: AppRole authentication
        if 'approle_role_id' in self.args and 'approle_secret_id' in self.args:
            logger.info("Using AppRole authentication")
            return await self._approle_login()

        raise ValueError(
            "No valid authentication method provided. "
            "Must provide one of: vault_token, vault_token_path, or approle credentials"
        )

    async def _read_token_from_file(self, token_path: str) -> str:
        """Read Vault token from file."""
        try:
            path = Path(token_path)
            if not path.exists():
                raise FileNotFoundError(f"Token file not found: {token_path}")

            token = path.read_text().strip()
            if not token:
                raise ValueError(f"Token file is empty: {token_path}")

            return token
        except Exception as e:
            logger.error(f"Failed to read token from file: {e}")
            raise

    async def _approle_login(self) -> str:
        """Authenticate using AppRole and return token."""
        role_id = self.args['approle_role_id']
        secret_id = self.args['approle_secret_id']

        login_url = f"{self.vault_url}/v1/auth/approle/login"
        payload = {
            'role_id': role_id,
            'secret_id': secret_id
        }

        headers = {}
        if self.namespace:
            headers['X-Vault-Namespace'] = self.namespace

        ssl_context = self._create_ssl_context()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    login_url,
                    json=payload,
                    headers=headers,
                    ssl=ssl_context
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(
                            f"AppRole login failed with status {response.status}: {error_text}"
                        )

                    data = await response.json()
                    token = data.get('auth', {}).get('client_token')

                    if not token:
                        raise ValueError("No token returned from AppRole login")

                    logger.info("AppRole authentication successful")
                    return token
        except Exception as e:
            logger.error(f"AppRole authentication failed: {e}")
            raise

    def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Create SSL context for HTTPS connections."""
        if not self.verify_ssl:
            return False

        if self.ca_cert_path:
            ssl_context = ssl.create_default_context(cafile=self.ca_cert_path)
            return ssl_context

        return None


class VaultWebSocketClient:
    """Manages WebSocket connection to Vault events API."""

    def __init__(self, vault_url: str, token: str, args: Dict[str, Any]):
        self.vault_url = vault_url.rstrip('/')
        self.token = token
        self.args = args
        self.namespace = args.get('vault_namespace')
        self.verify_ssl = args.get('verify_ssl', True)
        self.ca_cert_path = args.get('ca_cert_path')
        self.ping_interval = args.get('ping_interval', 20)
        self.ping_timeout = args.get('ping_timeout', 20)

    async def connect(self, event_type: str):
        """
        Connect to Vault WebSocket events API for a specific event type.

        Args:
            event_type: Event type to subscribe to (e.g., "*", "kv-v2/*", "audit/*")

        Returns:
            WebSocket connection
        """
        ws_url = self._build_ws_url(event_type)
        headers = self._build_headers()
        ssl_context = self._create_ssl_context()

        logger.info(f"Connecting to Vault WebSocket: {ws_url}")

        try:
            websocket = await websockets.connect(
                ws_url,
                additional_headers=headers,
                ssl=ssl_context,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout
            )
            logger.info(f"Connected to Vault events for type: {event_type}")
            return websocket
        except Exception as e:
            logger.error(f"Failed to connect to Vault WebSocket: {e}")
            raise

    def _build_ws_url(self, event_type: str) -> str:
        """Build WebSocket URL for Vault events API."""
        parsed = urlparse(self.vault_url)
        ws_scheme = 'wss' if parsed.scheme == 'https' else 'ws'
        ws_url = f"{ws_scheme}://{parsed.netloc}/v1/sys/events/subscribe/{event_type}?json=true"
        return ws_url

    def _build_headers(self) -> Dict[str, str]:
        """Build headers for WebSocket connection."""
        headers = {
            'X-Vault-Token': self.token
        }

        if self.namespace:
            headers['X-Vault-Namespace'] = self.namespace

        return headers

    def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Create SSL context for WebSocket connection."""
        if not self.verify_ssl:
            return None

        if self.ca_cert_path:
            ssl_context = ssl.create_default_context(cafile=self.ca_cert_path)
            return ssl_context

        return True


class ReconnectionManager:
    """Manages reconnection logic with exponential backoff."""

    def __init__(self, args: Dict[str, Any]):
        self.enabled = args.get('reconnect_enabled', True)
        self.max_attempts = args.get('reconnect_max_attempts', -1)
        self.initial_delay = args.get('reconnect_initial_delay', 1.0)
        self.max_delay = args.get('reconnect_max_delay', 60.0)
        self.backoff_multiplier = args.get('reconnect_backoff_multiplier', 2.0)
        self.current_attempt = 0

    def should_reconnect(self) -> bool:
        """Check if reconnection should be attempted."""
        if not self.enabled:
            logger.info("Reconnection disabled")
            return False

        # -1 means infinite attempts
        if self.max_attempts == -1:
            return True

        if self.current_attempt >= self.max_attempts:
            logger.error(f"Max reconnection attempts ({self.max_attempts}) reached")
            return False

        return True

    async def wait_before_reconnect(self):
        """Wait before attempting reconnection with exponential backoff and jitter."""
        # Calculate delay with exponential backoff
        delay = min(
            self.initial_delay * (self.backoff_multiplier ** self.current_attempt),
            self.max_delay
        )

        # Add jitter (±25%)
        jitter = delay * 0.25 * (2 * random.random() - 1)
        total_delay = delay + jitter

        logger.info(
            f"Waiting {total_delay:.2f}s before reconnection attempt "
            f"{self.current_attempt + 1}"
        )

        await asyncio.sleep(total_delay)
        self.current_attempt += 1

    def reset(self):
        """Reset reconnection counter after successful connection."""
        if self.current_attempt > 0:
            logger.info("Connection successful, resetting reconnection counter")
        self.current_attempt = 0


class EventProcessor:
    """Processes Vault CloudEvents and transforms them for EDA."""

    def __init__(self, args: Dict[str, Any]):
        self.args = args

    def process_event(self, raw_event: str) -> Optional[Dict[str, Any]]:
        """
        Process a raw CloudEvent from Vault and transform it for EDA.

        CloudEvents structure from Vault:
        {
          "id": "event-uuid",
          "source": "vault://cluster",
          "specversion": "1.0",
          "type": "*",
          "data": {
            "event_type": "kv-v2/data-write",
            "metadata": {"path": "secret/data/foo", "operation": "write"},
            "plugin_info": {"mount_path": "secret/", "plugin": "kv"}
          },
          "time": "2025-06-12T15:19:49Z"
        }

        Transformed output for EDA:
        {
          "vault": {
            "event_type": "kv-v2/data-write",
            "metadata": {...},
            "plugin_info": {...}
          },
          "cloudevents": {
            "id": "event-uuid",
            "source": "vault://cluster",
            "time": "2025-06-12T15:19:49Z"
          }
        }

        Args:
            raw_event: Raw event string from WebSocket

        Returns:
            Transformed event dict, or None if processing fails
        """
        try:
            cloud_event = json.loads(raw_event)

            # Extract data section
            data = cloud_event.get('data', {})
            if not data:
                logger.warning(f"Event missing data section: {cloud_event.get('id')}")
                return None

            # Vault 2.0+: metadata is nested under data.event.metadata
            # Vault 1.x:  metadata is directly under data.metadata
            event_inner = data.get('event', {})
            metadata = event_inner.get('metadata', data.get('metadata', {}))

            # Build transformed event
            event = {
                'vault': {
                    'event_type': data.get('event_type', 'unknown'),
                    'metadata': metadata,
                    'plugin_info': data.get('plugin_info', {})
                },
                'cloudevents': {
                    'id': cloud_event.get('id', ''),
                    'source': cloud_event.get('source', ''),
                    'time': cloud_event.get('time', '')
                }
            }

            logger.debug(f"Processed event: {event['vault']['event_type']}")
            return event

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse event JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to process event: {e}")
            return None


async def main(queue: asyncio.Queue, args: Dict[str, Any]):
    """
    Main entry point for the Vault events EDA plugin.

    This function is called by ansible-rulebook to start the event source.
    It maintains a WebSocket connection to Vault's events API and publishes
    events to the queue for processing by EDA rules.

    Args:
        queue: asyncio.Queue to publish events to
        args: Plugin configuration parameters

    Raises:
        ValueError: If required parameters are missing
        asyncio.CancelledError: On graceful shutdown
    """
    # Validate required parameters
    if 'vault_url' not in args or not args['vault_url']:
        raise ValueError("vault_url is required")

    vault_url = args['vault_url'].rstrip('/')
    event_types = args.get('event_types', ['*'])

    if not isinstance(event_types, list):
        event_types = [event_types]

    logger.info(f"Starting Vault events plugin for: {vault_url}")
    logger.info(f"Subscribing to event types: {event_types}")

    # Initialize components
    authenticator = VaultAuthenticator(vault_url, args)
    reconnection_mgr = ReconnectionManager(args)
    event_processor = EventProcessor(args)

    websocket = None

    # Main loop with reconnection support
    while True:
        try:
            # Authenticate with Vault
            logger.info("Authenticating with Vault...")
            token = await authenticator.authenticate()

            # Create WebSocket client
            ws_client = VaultWebSocketClient(vault_url, token, args)

            # For now, subscribe to first event type
            # TODO: Support multiple concurrent subscriptions
            event_type = event_types[0]

            # Connect to WebSocket
            websocket = await ws_client.connect(event_type)

            # Reset reconnection counter on successful connection
            reconnection_mgr.reset()

            # Process events
            logger.info("Listening for Vault events...")
            async for message in websocket:
                try:
                    # Process event
                    event = event_processor.process_event(message)

                    if event:
                        # Publish to EDA queue
                        await queue.put(event)

                        # Required by EDA: yield control to event loop
                        await asyncio.sleep(0)

                except Exception as e:
                    logger.error(f"Error processing event: {e}")
                    # Continue processing other events
                    continue

        except asyncio.CancelledError:
            # Graceful shutdown requested
            logger.info("Shutdown requested, closing connection...")
            if websocket:
                await websocket.close()
            raise

        except Exception as e:
            logger.error(f"Connection error: {e}")

            # Close existing connection if any
            if websocket:
                try:
                    await websocket.close()
                except Exception:
                    pass

            # Check if we should reconnect
            if not reconnection_mgr.should_reconnect():
                logger.error("Reconnection disabled or max attempts reached, exiting")
                raise

            # Wait before reconnecting
            await reconnection_mgr.wait_before_reconnect()
            logger.info("Attempting to reconnect...")


if __name__ == "__main__":
    # This allows testing the plugin standalone
    print("This is an EDA event source plugin. Use with ansible-rulebook.")
