#!/opr/osm/inn/apps/miniconda3/bin/python3
# requires python > 3.10, therefore we use miniconda python3, TODO: put to a blueprint

"""
Disk Quota Monitoring Script

This Python script is designed to check disk quotas *by project* on Lustre filesystems, with optional debug mode 
for detailed logging. It allows users to specify directories for checking disk quotas or defaults 
to user-specific directories if none are provided.

- Fetches and analyzes disk quotas (space and file quotas) for specified directories.
- Allows setting thresholds to trigger warnings when disk usage exceeds the specified percentage.
- Supports optional debug logging for troubleshooting and detailed command outputs.
- Uses Lustre-specific commands (`lfs` and `df`) to gather disk usage and quota information.

Usage:
  ./quota.py [options] [paths]

Arguments:
  -d, --debug        Enable debug output for detailed logs.
  paths              List of directories to check (default: user directories if none are provided).
"""


from pathlib import Path
from dataclasses import dataclass
import subprocess
import os
import sys
import argparse
import logging
import time
import requests

logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(levelname)s - %(message)s')
handler.setFormatter(formatter)


def main():
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

    # Initialize the argument parser
    parser = argparse.ArgumentParser(
        description="A script to find out disk quota and whether they pass a threshold, with debug options."
    )
    
    parser.add_argument(
        '-d', '--debug', 
        action='store_true', 
        help='Enable debug output'
    )
    
    parser.add_argument(
        '-w', '--warn', 
        action='store_true', 
        help='Warn if exceeding threshold'
    )

    # Positional argument for directories
    parser.add_argument(
        'paths', 
        nargs='*',  # Accept zero or more positional paths
        type=Path,
        help='List of directories to check (default: user directories if none are provided)'
    )

    args = parser.parse_args()

    if help in args:
        parser.print_help()
        sys.exit(1)

    # Handle the logic based on parsed arguments

    if args.debug:
        logger.setLevel(logging.DEBUG)
        handler.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")
    else:
        logger.setLevel(logging.INFO)
        handler.setLevel(logging.INFO)
    
    logger.addHandler(handler)

    directories = args.paths if args.paths else [
        Path(os.getenv('HOME')),
        Path(f"/scratch/mch"),
        Path(f"/opr"),
        Path('/store_new/mch'),
        Path(f"/scratch/d1000"),
    ]

    for dir in directories:
        if dir.exists() and dir.is_dir():
            run(dir, args.debug, args.warn, GRAFANA_URL, GRAFANA_TOKEN)
        else:
            logger.debug(f"skipping {dir}, it does not exist")

@dataclass
class Quota:
    type: str
    used: str
    quota: str
    limit: str

@dataclass
class DiskQuota:
    filesystem: str
    space: Quota
    files: Quota
    
def send_to_grafana(grafana_url: str, grafana_token: str, filesystem: str, quota_type: str,
                    percent: float, used: float, free: float) -> None:
    """Send quota metrics to Grafana via InfluxDB line protocol."""
    timestamp_ns = int(time.time() * 1e9)
    fs_tag = filesystem.replace(',', r'\,').replace(' ', r'\ ').replace('=', r'\=')
    line = (
        f"disk_quota,filesystem={fs_tag},type={quota_type} "
        f"percent={percent:.4f},used={used:.0f},free={free:.0f} {timestamp_ns}"
    )
    url = f"{grafana_url.rstrip('/')}"
    headers = {
        "Authorization": f"Bearer {grafana_token}",
        "Content-Type": "text/plain",
    }
    try:
        response = requests.post(url, data=line, headers=headers, timeout=10)
        response.raise_for_status()
        logger.debug(f"Sent metrics to Grafana for {filesystem} ({quota_type})")
    except requests.RequestException as e:
        logger.error(f"Failed to send metrics to Grafana for {filesystem} ({quota_type}): {e}")


def get_lfs_project(dir: Path, debug: bool = False) -> int:

    if dir.exists() and dir.is_dir():

        cmd = ['lfs', 'project', '-d', str(dir)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError:
            logger.debug(f"unsuccessful run of command {cmd}")
            return 0
        
        logger.debug(f"Output of command: {' '.join(cmd)}")
        logger.debug(result.stdout)

        project = int(result.stdout.strip().split(' ')[0])
        return project
    
    else:
        raise RuntimeError(f'{dir} does not exist.')

def get_mount_point_of_dir(dir: Path, debug: bool = False) -> Path:

    if dir.exists() and dir.is_dir():

        cmd = ['df', '--output=target', str(dir)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        logger.debug(f"Output of command: {' '.join(cmd)}")
        logger.debug(result.stdout)

        if not result.returncode == 0:
            raise RuntimeError(f'Could not get mount point for directory: {dir}')
        
        target = Path(result.stdout.split('\n')[1])
        return target
    
    else:
        raise RuntimeError(f'{dir} does not exist.')


def get_lfs_disk_quotas_for_project(project: int, mount_target: Path, debug: bool = False) -> DiskQuota:

    cmd = ['lfs', 'quota', '-p', str(project), str(mount_target)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    if not result.returncode == 0:
        raise RuntimeError(f'Could not get project for directory: {dir}')
    
    lines = result.stdout.strip().split('\n')

    logger.debug(f"Output of command: {' '.join(cmd)}")
    logger.debug(result.stdout)

    info = list(zip(lines[1].strip().split(), lines[2].strip().split()))

    filesystem = dict(info[0:1])
    space_info = dict(info[1:4])
    files_info = dict(info[5:8])

    return DiskQuota(filesystem = filesystem.get('Filesystem'),
        space = Quota(type = 'space',
                            used = space_info.get('kbytes'),
                            quota = space_info.get('quota'),
                            limit = space_info.get('limit')),
        files = Quota(type = 'files',
                            used = files_info.get('files'),
                            quota = files_info.get('quota'),
                            limit = files_info.get('limit')))

def get_df_disk_quota(path: Path, debug: bool = False) -> DiskQuota:

    cmd = ['df', str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    if not result.returncode == 0:
        raise RuntimeError(f'Could not get df for directory: {path}')
    
    lines = result.stdout.strip().split('\n')

    logger.debug(f"Output of command: {' '.join(cmd)}")
    logger.debug(result.stdout)
    info = lines[1].strip().split()
    space_used = info[2]
    space_limit = info[1]

    return DiskQuota(filesystem = str(path),
        space = Quota(type = 'space',
                            used = space_used,
                            quota = None,
                            limit = space_limit),
        files = Quota(type = 'files',
                            used = 0,
                            quota = 0,
                            limit = 0))
        



def sizeof_fmt(num: int, suffix="B") -> str:
    """Provide num in bytes"""
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024.0:
            return f"{num:5.3f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"


def run(path: Path, debug: bool, warn: bool, grafana_url: str, grafana_token: str):

    logger.debug(f"Inspecting directory: {path}")

    project = get_lfs_project(path, debug)
    if project == 0:
        logger.debug(f"{path} has no assigned project, querying space quota with df")
        disk_quotas = get_df_disk_quota(path,debug)
    else:
        logger.debug(f"querying {path} space and files quotas with lfs disk quota")
        mount_target = get_mount_point_of_dir(path, debug)
        disk_quotas = get_lfs_disk_quotas_for_project(project, mount_target, debug)


    for quota in (disk_quotas.space, disk_quotas.files):

        if float(quota.limit) > 0: 
            percent = float(quota.used) / float(quota.limit) * 100

            if quota.type == 'space':
                used_val = float(quota.used)
                free_val = float(quota.limit) - float(quota.used)
                send_to_grafana(grafana_url, grafana_token, disk_quotas.filesystem,
                                'space', percent, used_val, free_val)

            elif quota.type == 'files':
                used_val = float(quota.used)
                free_val = float(quota.limit) - float(quota.used)
                send_to_grafana(grafana_url, grafana_token, disk_quotas.filesystem,
                                'files', percent, used_val, free_val)
                    
        else:
            logger.debug(f'No quota set for {quota.type}')


if __name__ == "__main__":
    main()

    # TODO: Find out whether we need to log user limits as well
