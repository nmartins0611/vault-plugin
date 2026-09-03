#!/usr/bin/env python3
"""Write or delete a KV v2 secret to generate a Vault audit event."""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


DEMO_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = DEMO_DIR / ".env"
SECRET_PATH = "secret/data/eda-demo/app"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value)


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def vault_request(
    addr: str,
    method: str,
    path: str,
    token: str,
    body: Optional[Dict[str, Any]],
) -> tuple[int, Dict[str, Any]]:
    payload = None if body is None else json.dumps(body).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Vault-Token": token,
    }
    request = urllib.request.Request(
        addr.rstrip("/") + path,
        data=payload,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["write", "delete"])
    parsed = parser.parse_args()

    load_env_file(ENV_FILE)
    addr = require_env("VAULT_ADDR")
    token = require_env("VAULT_TOKEN")

    if parsed.action == "write":
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for i in range(16))
        stamp = str(int(time.time()))
        status, body = vault_request(
            addr,
            "POST",
            f"/v1/{SECRET_PATH}",
            token,
            {"data": {"password": password, "rotated_at": stamp, "source": "eda-demo"}},
        )
        if status not in (200, 204):
            raise RuntimeError(f"Secret write failed ({status}): {body}")
        print(f"Wrote {SECRET_PATH} rotated_at={stamp} password=***")
        return

    status, body = vault_request(addr, "DELETE", f"/v1/{SECRET_PATH}", token, None)
    if status not in (200, 204):
        raise RuntimeError(f"Secret delete failed ({status}): {body}")
    print(f"Deleted {SECRET_PATH}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
