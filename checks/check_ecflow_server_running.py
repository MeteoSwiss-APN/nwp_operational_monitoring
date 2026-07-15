#!/usr/bin/env python3
"""
check_ecflow_server.py

Checks whether the ecFlow server is responding and pushes a status metric
to Grafana Cloud (InfluxDB line-protocol endpoint).

Metric value:
  0  -> server is responding  (OK)
  1  -> server is not responding  (DOWN)

Usage:
    python3 check_ecflow_server.py --host <ECF_HOST> --port <ECF_PORT>

Exit codes:
    0  -> ecFlow server is running
    1  -> ecFlow server is not responding
    2  -> Grafana push failed
"""
from pathlib import Path
import argparse
import os
import subprocess
import sys
import urllib.error
import urllib.request

try:
    import ecflow
    _HAS_ECFLOW = True
except ImportError:
    _HAS_ECFLOW = False


credentials_file = Path(__file__).parent.parent / "includes" / ".credentials"

if not credentials_file.is_file():
    print(f"[ERROR] Credentials file not found: {credentials_file}", file=sys.stderr)
    sys.exit(1)

_creds: dict = {}
with open(credentials_file) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        _creds[key.strip()] = value.strip().strip('"').strip("'")

GRAFANA_URL   = _creds["GRAFANA_URL"]
GRAFANA_TOKEN = _creds["GRAFANA_TOKEN"]
ECFLOW_DIR    = os.environ.get("ECFLOW_DIR", _creds.get("ECFLOW_DIR", ""))


def ping_ecflow(host: str, port: str) -> bool:
    """Return True if the ecFlow server responds to a ping."""
    if _HAS_ECFLOW:
        try:
            client = ecflow.Client(host, port)
            client.ping()
            return True
        except ecflow.RuntimeError:
            return False
        except Exception as exc:
            print(f"ecflow ping error: {exc}", file=sys.stderr)
            return False

    # Fallback: use ecflow_client binary
    ecflow_client = os.path.join(ECFLOW_DIR, "bin", "ecflow_client")
    cmd = [ecflow_client, "--ping", f"--host={host}", f"--port={port}"]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"ecflow_client ping timed out for {host}:{port}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print(f"ecflow_client not found (ECFLOW_DIR={ECFLOW_DIR!r})", file=sys.stderr)
        return False


def push_metric(host: str, is_running: bool) -> bool:
    """
    Push ecFlow server status to Grafana Cloud using InfluxDB line protocol.
    Returns True on success, False on failure.
    """
    value = 0 if is_running else 1
    line = f"ecflow_server_status,host={host} value={value}i"

    req = urllib.request.Request(
        GRAFANA_URL,
        data=line.encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GRAFANA_TOKEN}",
            "Content-Type": "text/plain",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                print(f"Grafana returned unexpected HTTP {resp.status}", file=sys.stderr)
                return False
        return True
    except urllib.error.HTTPError as exc:
        print(f"Grafana HTTP error {exc.code}: {exc.reason}", file=sys.stderr)
        return False
    except urllib.error.URLError as exc:
        print(f"Failed to reach Grafana at {GRAFANA_URL}: {exc.reason}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check ecFlow server status and push metric to Grafana Cloud."
    )
    parser.add_argument("--host", default=os.environ.get("ECF_HOST", "balfrin-ln003"),
                        help="ecFlow server host (default: $ECF_HOST or balfrin-ln003)")
    parser.add_argument("--port", default=os.environ.get("ECF_PORT", "32461"),
                        help="ecFlow server port (default: $ECF_PORT or 32461)")
    args = parser.parse_args()

    is_running = ping_ecflow(args.host, args.port)

    if not push_metric(args.host, is_running):
        print("WARNING: metric push to Grafana failed", file=sys.stderr)
        return 2

    if is_running:
        print(f"ecFlow server {args.host}:{args.port} is running (metric value=0 pushed)")
        return 0
    else:
        print(f"ecFlow server {args.host}:{args.port} is not responding (metric value=1 pushed)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
