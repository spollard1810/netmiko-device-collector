# Netmiko Device Collector

Pulls `show version`, `show interface status`, and `show running-config` from a list of devices and saves a labelled report per hostname.

## Setup

```bash
pip install -r requirements.txt
cp ips.txt.example ips.txt   # then edit with your device IPs
```

## Usage

```bash
python collect_configs.py              # reads ips.txt
python collect_configs.py devices.txt  # custom IP list
python collect_configs.py -w 10        # 10 devices in parallel (default 5)
```

You'll be prompted for username, password, and an optional enable secret.

## How it works

1. Loads IPs from the text file (blank lines, `#` comments and duplicates are skipped).
2. Uses Netmiko `SSHDetect` to auto-detect each device type (falls back to `cisco_ios`).
3. Runs the three commands and grabs the hostname from the prompt.
4. Writes `output/<hostname>_<ip>.txt` with a header (hostname, IP, device type, timestamp) and a labelled section per command.
5. Writes `output/_summary.txt` listing success/failure per device.

The `output/` folder is created automatically and is git-ignored, as is `ips.txt`, so configs and device lists don't get committed.
