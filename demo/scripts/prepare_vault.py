#!/usr/bin/env python3
"""Unseal vault.nostromo.io, enable KV audit, and confirm the demo path."""

import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


DEMO_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = DEMO_DIR / ".env"
AUDIT_DEVICE_NAME = "eda-file"
SAFE_PATH = re.compile(r"^/[A-Za-z0-9._/-]+$")


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
        raise RuntimeError(f"{name} is not set. Copy demo/.env.example to demo/.env.")
    return value


def vault_request(
    addr: str,
    method: str,
    path: str,
    token: Optional[str],
    body: Optional[Dict[str, Any]],
) -> tuple[int, Dict[str, Any]]:
    payload = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Vault-Token"] = token
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


def run_ssh(user: str, host: str, command: str) -> None:
    target = f"{user}@{host}"
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            target,
            command,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"SSH to {target} failed: {result.stderr.strip() or result.stdout.strip()}"
        )


def main() -> None:
    load_env_file(ENV_FILE)
    addr = require_env("VAULT_ADDR")
    token = require_env("VAULT_TOKEN")
    unseal_key = require_env("VAULT_UNSEAL_KEY")
    ssh_host = require_env("VAULT_SSH_HOST")
    ssh_user = require_env("VAULT_SSH_USER")
    audit_path = require_env("VAULT_AUDIT_PATH")

    if not SAFE_PATH.fullmatch(audit_path):
        raise RuntimeError(f"Unsafe VAULT_AUDIT_PATH: {audit_path}")

    status_code, seal = vault_request(addr, "GET", "/v1/sys/seal-status", None, None)
    if status_code != 200:
        raise RuntimeError(f"seal-status failed: {seal}")
    print(
        f"Vault {seal.get('version')} at {addr} sealed={seal.get('sealed')} "
        f"storage={seal.get('storage_type')}"
    )

    if seal.get("sealed"):
        status_code, unsealed = vault_request(
            addr, "PUT", "/v1/sys/unseal", None, {"key": unseal_key}
        )
        if status_code != 200 or unsealed.get("sealed"):
            raise RuntimeError(f"Unseal failed: {unsealed}")
        print("Vault unsealed")

    health_code, health = vault_request(addr, "GET", "/v1/sys/health", None, None)
    if health.get("sealed"):
        raise RuntimeError("Vault is still sealed after unseal")
    print(
        f"Health http={health_code} version={health.get('version')} "
        f"enterprise={health.get('enterprise')}"
    )

    token_code, lookup = vault_request(addr, "GET", "/v1/auth/token/lookup-self", token, None)
    if token_code != 200:
        raise RuntimeError(f"Token lookup failed: {lookup}")
    print(f"Token policies: {(lookup.get('data') or {}).get('policies')}")

    audit_dir = str(Path(audit_path).parent)
    run_ssh(
        ssh_user,
        ssh_host,
        (
            f"mkdir -p {shlex.quote(audit_dir)} && "
            f"chown vault:vault {shlex.quote(audit_dir)} && "
            f"chmod 750 {shlex.quote(audit_dir)}"
        ),
    )
    print(f"Audit directory ready: {audit_dir}")

    list_code, audits = vault_request(addr, "GET", "/v1/sys/audit", token, None)
    if list_code != 200:
        raise RuntimeError(f"Listing audit devices failed: {audits}")
    devices = audits.get("data") or audits
    device_key = f"{AUDIT_DEVICE_NAME}/"
    if device_key in devices:
        print(f"Audit device {AUDIT_DEVICE_NAME} already enabled")
    else:
        enable_code, enabled = vault_request(
            addr,
            "PUT",
            f"/v1/sys/audit/{AUDIT_DEVICE_NAME}",
            token,
            {
                "type": "file",
                "options": {
                    "file_path": audit_path,
                },
            },
        )
        if enable_code not in (200, 204):
            raise RuntimeError(f"Enabling audit device failed: {enabled}")
        print(f"Enabled file audit device {AUDIT_DEVICE_NAME} -> {audit_path}")

    run_ssh(ssh_user, ssh_host, f"test -f {shlex.quote(audit_path)} && echo audit_file_ok")
    print("Vault is ready for the EDA demo")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
