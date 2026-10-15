#!/usr/bin/env python3
"""
Collect 'show version', 'show interface status' and 'show running-config'
from a list of network devices.

- Reads IP addresses from a text file (one per line, '#' comments allowed)
- Prompts for username / password (and optional enable secret)
- Uses Netmiko SSHDetect to auto-detect the device type
- Writes one labelled .txt file per device into ./output/

Usage:
    python collect_configs.py                 # uses ips.txt
    python collect_configs.py my_devices.txt
    python collect_configs.py ips.txt -w 10   # 10 devices in parallel
"""

import argparse
import getpass
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from netmiko import ConnectHandler, SSHDetect
from netmiko.exceptions import (
    NetmikoAuthenticationException,
    NetmikoTimeoutException,
)

COMMANDS = [
    ("SHOW VERSION", "show version"),
    ("SHOW INTERFACE STATUS", "show interface status"),
    ("SHOW RUNNING-CONFIG", "show running-config"),
]

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
BANNER_WIDTH = 80


def load_ips(path: Path) -> list[str]:
    """Read IPs from file, skipping blanks, comments and duplicates."""
    if not path.is_file():
        sys.exit(f"[!] IP file not found: {path}")
    ips = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line and line not in ips:
            ips.append(line)
    if not ips:
        sys.exit(f"[!] No IP addresses found in {path}")
    return ips


def banner(title: str, char: str = "=") -> str:
    line = char * BANNER_WIDTH
    return f"{line}\n{title.center(BANNER_WIDTH)}\n{line}\n"


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def detect_device_type(base: dict) -> str:
    """Use Netmiko autodetect; fall back to cisco_ios if unsure."""
    guesser = SSHDetect(**{**base, "device_type": "autodetect"})
    try:
        best = guesser.autodetect()
    finally:
        guesser.connection.disconnect()
    return best or "cisco_ios"


def collect(ip: str, username: str, password: str, secret: str) -> tuple[str, str]:
    """Connect to one device and write its report. Returns (ip, status msg)."""
    base = {
        "host": ip,
        "username": username,
        "password": password,
        "secret": secret or password,
        "conn_timeout": 15,
        "auth_timeout": 20,
    }

    try:
        device_type = detect_device_type(base)
        with ConnectHandler(**{**base, "device_type": device_type}) as conn:
            if secret and not conn.check_enable_mode():
                try:
                    conn.enable()
                except Exception:
                    pass  # not all platforms support/need enable

            hostname = conn.find_prompt().strip("#>$ ").strip() or ip
            # Strip config-mode style suffixes like "R1(config)"
            hostname = re.sub(r"\(.*\)$", "", hostname)

            sections = []
            for label, cmd in COMMANDS:
                try:
                    out = conn.send_command(cmd, read_timeout=120)
                except Exception as exc:  # keep going if one command fails
                    out = f"[ERROR running '{cmd}': {exc}]"
                sections.append(banner(f"{label}  ({cmd})", "-") + out.rstrip() + "\n")

    except NetmikoAuthenticationException:
        return ip, "FAILED - authentication error"
    except NetmikoTimeoutException:
        return ip, "FAILED - connection timed out"
    except Exception as exc:
        return ip, f"FAILED - {type(exc).__name__}: {exc}"

    header = banner(f"HOSTNAME: {hostname}") + (
        f"IP Address   : {ip}\n"
        f"Device Type  : {device_type}\n"
        f"Collected    : {datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
    )
    report = header + "\n".join(sections)

    out_file = OUTPUT_DIR / f"{safe_filename(hostname)}_{safe_filename(ip)}.txt"
    out_file.write_text(report, encoding="utf-8")
    return ip, f"OK - {hostname} ({device_type}) -> {out_file.name}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ip_file", nargs="?", default="ips.txt",
                        help="text file with one IP per line (default: ips.txt)")
    parser.add_argument("-w", "--workers", type=int, default=5,
                        help="number of devices to query in parallel (default: 5)")
    args = parser.parse_args()

    ips = load_ips(Path(args.ip_file))
    print(f"[*] Loaded {len(ips)} device(s) from {args.ip_file}")

    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    secret = getpass.getpass("Enable secret (blank = same as password / none): ")

    OUTPUT_DIR.mkdir(exist_ok=True)

    results = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(collect, ip, username, password, secret): ip for ip in ips}
        for fut in as_completed(futures):
            ip, status = fut.result()
            results[ip] = status
            print(f"  {ip:<18} {status}")

    ok = sum(1 for s in results.values() if s.startswith("OK"))
    summary = [banner("COLLECTION SUMMARY"),
               f"Run at: {datetime.now():%Y-%m-%d %H:%M:%S}",
               f"Success: {ok}/{len(ips)}\n"]
    summary += [f"{ip:<18} {results[ip]}" for ip in ips]
    (OUTPUT_DIR / "_summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"\n[*] Done: {ok}/{len(ips)} succeeded. Output in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
