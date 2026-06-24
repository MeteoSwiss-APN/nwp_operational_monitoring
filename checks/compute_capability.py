#!/opr/osm/inn/apps/miniconda3/bin/python3
import json
import subprocess
import time
import requests
import sys
from pathlib import Path
from collections import defaultdict


def get_nodes():
    out = subprocess.check_output(
        ["scontrol", "show", "node", "--json"],
        text=True
    )
    return json.loads(out)
    
def classify(node):
    state_raw = node.get("state", [])

    if isinstance(state_raw, str):
        state_raw = [state_raw]

    states = {s.upper() for s in state_raw}

    # CPU vs GPU
    gres = node.get("gres", "").lower()
    node_class = "gpu" if "gpu:" in gres else "cpu"

    reservation = bool(node.get("reservation", ""))

    # 1. unavailable_technical
    if "DOWN" in states or "FAIL" in states or "NOT_RESPONDING" in states:
        capability = "zunavailable_technical"

    # 2. unavailable_administrative
    elif "DRAIN" in states or "DRAINED" in states or "MAINT" in states:
        capability = "zunavailable_administrative"

    # 3. allocated
    elif "ALLOCATED" in states:

        if reservation:
            capability = "utilized_reserved"
        else:       

            capability = "utilized"

    # 4. idle
    elif "IDLE" in states:

        if reservation:
            capability = "available_reserved"
        else:
            capability = "available"

    # 5. others
    else:
        capability = "other"

    return node_class, capability


def collect():
    data = get_nodes()

    counters = defaultdict(int)

    for node in data["nodes"]:
        node_class, node_state = classify(node)
        counters[(node_class, node_state)] += 1

    return counters

def send_to_influx(
    grafana_url: str,
    grafana_token: str,
    counters: dict
    ) -> None:

    timestamp_ns = int(time.time() * 1e9)

    lines = []

    for (node_class, state), value in counters.items():

        class_tag = str(node_class).replace(',', r'\,').replace(' ', r'\ ').replace('=', r'\=')
        state_tag = str(state).replace(',', r'\,').replace(' ', r'\ ').replace('=', r'\=')

        line = (
            f"slurm_nodes,class={class_tag},state={state_tag} "
            f"value={value} {timestamp_ns}"
        )

        lines.append(line)

    payload = "\n".join(lines)

    url = grafana_url.rstrip("/")

    headers = {
        "Authorization": f"Bearer {grafana_token}",
        "Content-Type": "text/plain",
    }

    try:
        response = requests.post(
            url,
            data=payload,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()

    except requests.RequestException as e:
        print(f"Failed to send Slurm metrics to Grafana/Influx: {e}")


if __name__ == "__main__":
    counters = collect()
    
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
    send_to_influx(GRAFANA_URL, GRAFANA_TOKEN, counters)
