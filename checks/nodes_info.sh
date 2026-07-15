#!/bin/bash
#
# nodes_info.sh - Display and filter Slurm HPC node information
#
# This script lists HPC compute nodes with their type (CPU or GPU) and state,
# using Slurm commands (`sinfo` and `scontrol`). It supports filters for
# unhealthy nodes, node type, and prints healthy node counts by type.
#
# Usage:
#   ./nodes_info.sh [-u] [-c] [-g] [-n] [-h]
#
# Options:
#   -u    Show only unhealthy nodes (e.g., DOWN, DRAIN, FAIL, etc.)
#   -c    Show only CPU nodes
#   -g    Show only GPU nodes
#   -n    Show healthy node count (separated by CPU and GPU)
#   -h    Show this help message and exit
#
# Examples:
#   ./nodes_info.sh
#       List all nodes with their type and state
#
#   ./nodes_info.sh -u
#       List only unhealthy nodes
#
#   ./nodes_info.sh -g -n
#       Show GPU nodes and print count of healthy GPU nodes
#
# Requirements:
#   - Slurm tools: sinfo, scontrol
#   - Run on a system with appropriate Slurm access
#
# Author: Daniel Leuenberger
# Last updated: 2026-06-12

# blank-separated list of known unhealthy nodes (e.g. in maintenance)
# they are ignored in the unhealthy nodes list query
# but not in the number of unhealthy nodes
# format: "nid002250,nid001250,..."
ignore_unhealthy_nodes=""

# ---------- Grafana Cloud Configuration ----------
CREDENTIALS_FILE="$(dirname "$0")/../includes/.credentials"
if [[ ! -f "$CREDENTIALS_FILE" ]]; then
    echo "[ERROR] Credentials file not found: $CREDENTIALS_FILE" >&2
    exit 1
fi
# shellcheck source=includes/credentials
source "$CREDENTIALS_FILE"

# The field 'up' is 1 when the node is healthy, 0 when unhealthy.
send_metrics_to_grafana() {
    local payload="$1"
    local http_code
    http_code=$(curl -s -o /tmp/grafana_push_response.txt -w "%{http_code}" \
        -X POST "${GRAFANA_URL}" \
        -u "${GRAFANA_TOKEN}" \
        -H "Content-Type: text/plain" \
        --data-binary "${payload}")
    if [[ "$http_code" != "204" && "$http_code" != "200" ]]; then
        echo "[ERROR] Grafana push failed (HTTP ${http_code}): $(cat /tmp/grafana_push_response.txt)" >&2
        return 1
    fi
    echo "[OK] Metrics sent to Grafana Cloud (HTTP ${http_code})"
}

# ---------- Helper Functions ----------

# Determine node type (CPU or GPU) based on scontrol output
node_type_from_info () {
    echo "$1" | grep -qi "gpu" && echo "GPU" || echo "CPU"
}

# Extract node state from scontrol output
node_state_from_info () {
    echo "$1" | grep -o "State=[^ ]*" | cut -d= -f2
}

# Return all node info: name, type, state
# Extracts node names from 'scontrol show nodes' block headers (one block per node,
# no partition duplicates unlike sinfo -N)
nodes_info () {
    scontrol show nodes | grep "^NodeName=" | awk '{print $1}' | cut -d= -f2 | sort -u | while read -r node; do
        info=$(scontrol show node="$node")
        type=$(node_type_from_info "$info")
        state=$(node_state_from_info "$info")
        echo "$node $type $state"
    done
}

# Check whether a node state is unhealthy.
# Optionally, a node name can be given to skip nodes in the ignore list.
is_unhealthy() {
    # the node state
    local state="$1"
    # the node name (optional)
    local node="$2"

    # If node is given and in ignore list → treat as healthy
    if [[ -n "$node" && "$ignore_unhealthy_nodes" =~ "$node" ]]; then
        return 1
    fi

    # Otherwise check for unhealthy states
    [[ "$state" =~ DOWN|DRAIN|DRAINING|DRAINED|FAIL|FAILING|MAINT|MAINTENANCE|UNK|UNKNOWN|NOT_RESPONDING ]]
}

# ---------- Option Parsing ----------

show_unhealthy=false
show_cpu=false
show_gpu=false
show_healthy_count=false

while getopts "ucgnh" opt; do
    case "$opt" in
        u) show_unhealthy=true ;;
        c) show_cpu=true ;;
        g) show_gpu=true ;;
        n) show_healthy_count=true ;;
        h)
            sed -n '2,30p' "$0"  # Show documentation block from top of script
            exit 0
            ;;
        *) echo "Invalid option. Use -h for help." >&2; exit 1 ;;
    esac
done

# ---------- Main Logic ----------
host_name=$(hostname | cut -d'-' -f1)
timestamp_ns=$(date +%s%N)

healthy_cpu_count=0
healthy_gpu_count=0
grafana_payload=""

# Use process substitution to preserve variables in the loop
while read -r node type state; do
    # Filter: show only unhealthy nodes if -u given
    if $show_unhealthy && ! is_unhealthy "$state" "$node"; then
        continue
    fi

    # Filter: by type
    if $show_cpu && [[ "$type" != "CPU" ]]; then
        continue
    fi
    if $show_gpu && [[ "$type" != "GPU" ]]; then
        continue
    fi

    # Count healthy nodes by type if -n given
    if $show_healthy_count && ! is_unhealthy "$state"; then
        if [[ "$type" == "CPU" ]]; then
            ((healthy_cpu_count++))
        elif [[ "$type" == "GPU" ]]; then
            ((healthy_gpu_count++))
        fi
    fi

    # Build InfluxDB line protocol entry for this node
    # up=0 → healthy, up=1 → unhealthy
    up=0
    is_unhealthy "$state" "$node" && up=1
    line="slurm_node_status,host=${host_name},node=${node},type=${type} state=\"${state}\",up=${up}i ${timestamp_ns}"
    if [[ -z "$grafana_payload" ]]; then
        grafana_payload="$line"
    else
        grafana_payload="${grafana_payload}
${line}"
    fi
done < <(nodes_info)

# Send all metrics to Grafana Cloud in one request
if [[ -n "$grafana_payload" ]]; then
    send_metrics_to_grafana "$grafana_payload"
else
    echo "No nodes matched the selected filters — nothing sent to Grafana."
fi
