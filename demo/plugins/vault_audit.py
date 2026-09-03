"""
DOCUMENTATION:
  name: vault_audit
  short_description: Receive HashiCorp Vault / OpenBao audit events over SSH
  description:
    - Tails a Vault file audit device via SSH
    - Transforms audit JSON into an EDA-friendly structure
    - Drops request payloads so secret values never reach the rulebook
  options:
    ssh_host:
      description: Vault host to SSH into
      required: true
      type: str
    ssh_user:
      description: SSH user on the Vault host
      required: true
      type: str
    audit_path:
      description: Path of the file audit device on the Vault host
      required: true
      type: str
"""

import asyncio
import json
import logging
import re
import shlex
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def transform_audit_line(raw_line: str) -> Optional[Dict[str, Any]]:
    """Turn one Vault audit JSON line into an EDA event, or None to skip."""
    stripped = raw_line.strip()
    if not stripped:
        return None

    try:
        record = json.loads(stripped)
    except json.JSONDecodeError as exc:
        logger.warning("Skipping malformed audit line: %s", exc)
        return None

    if record.get("type") != "request":
        return None

    request = record.get("request")
    if not isinstance(request, dict):
        return None

    path = request.get("path", "")
    if not isinstance(path, str) or not path.startswith("secret/"):
        return None

    operation = request.get("operation", "unknown")
    return {
        "vault": {
            "operation": operation,
            "path": path,
            "mount": path.split("/", 1)[0],
        },
        "audit": {
            "type": record.get("type", ""),
            "time": record.get("time", ""),
        },
    }


async def _tail_audit_file(queue: asyncio.Queue, args: Dict[str, Any]) -> None:
    ssh_host = args["ssh_host"]
    ssh_user = args["ssh_user"]
    audit_path = args["audit_path"]
    if not re.fullmatch(r"/[A-Za-z0-9._/-]+", audit_path):
        raise ValueError(f"Unsafe audit_path: {audit_path}")
    target = f"{ssh_user}@{ssh_host}"

    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        target,
        f"tail -F -n 0 {shlex.quote(audit_path)}",
    ]
    logger.info("Tailing Vault audit log via SSH: %s:%s", target, audit_path)

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if process.stdout is None:
        raise RuntimeError("SSH process has no stdout pipe")

    try:
        while True:
            line = await process.stdout.readline()
            if not line:
                stderr = b""
                if process.stderr is not None:
                    stderr = await process.stderr.read()
                raise RuntimeError(
                    f"SSH audit tail ended unexpectedly: {stderr.decode().strip()}"
                )

            event = transform_audit_line(line.decode("utf-8", errors="replace"))
            if event is None:
                continue

            await queue.put(event)
            await asyncio.sleep(0)
    finally:
        if process.returncode is None:
            process.terminate()
            await process.wait()


async def main(queue: asyncio.Queue, args: Dict[str, Any]) -> None:
    required = ["ssh_host", "ssh_user", "audit_path"]
    missing = [name for name in required if not args.get(name)]
    if missing:
        raise ValueError(f"Missing required arguments: {', '.join(missing)}")

    delay = 1.0
    while True:
        try:
            await _tail_audit_file(queue, args)
        except asyncio.CancelledError:
            logger.info("Shutdown requested, stopping audit tail")
            raise
        except Exception as exc:
            logger.error("Audit tail failed: %s", exc)
            await asyncio.sleep(delay)
            delay = min(delay * 2.0, 30.0)
            logger.info("Retrying audit tail")
            continue
