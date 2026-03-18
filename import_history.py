#!/usr/bin/env python3
"""VPSに溜まった過去のFleet Telemetryログを一括インポート。"""

import json
import subprocess
import sys
from db import init_db, DB_PATH
from telemetry_bridge import parse_telemetry_record, insert_with_timestamp, latest_state

SSH_KEY = "/home/yuto/.ssh/oracle.key"
VPS = "ubuntu@168.138.203.197"


def main():
    init_db()

    # Reset state
    for k in latest_state:
        latest_state[k] = None

    print("[import] VPSから過去ログを取得中...")
    result = subprocess.run(
        [
            "ssh", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=no",
            VPS,
            "sudo", "journalctl", "-u", "fleet-telemetry",
            "--no-pager", "-o", "cat",
        ],
        capture_output=True, text=True,
    )

    count = 0
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        if msg.get("msg") != "record_payload":
            continue
        metadata = msg.get("metadata", {})
        if metadata.get("txtype") != "V":
            continue

        data = msg.get("data", {})
        row = parse_telemetry_record(data)
        if row is None:
            continue

        insert_with_timestamp(row)
        count += 1

    print(f"[import] {count}件インポート完了 → {DB_PATH}")


if __name__ == "__main__":
    main()
