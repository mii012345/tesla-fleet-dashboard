#!/usr/bin/env python3
"""
Fleet Telemetry → SQLite Bridge
VPSのFleet Telemetryログ(journald)をSSH経由でストリームし、
ローカルのSQLiteに蓄積する。ダッシュボード(server.py)がそのまま使える。
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from db import init_db, DB_PATH
import sqlite3

VPS_HOST = "168.138.203.197"
SSH_KEY = "/home/yuto/.ssh/oracle.key"
SSH_USER = "ubuntu"

# Fleet Telemetryフィールド → SQLiteカラムのマッピング
# 車は変化があったフィールドだけ送ってくるので、最新値をキャッシュして
# 完全な行を作る
latest_state = {
    "latitude": None,
    "longitude": None,
    "speed": None,
    "heading": None,
    "shift_state": None,
    "power": None,
    "battery_level": None,
    "battery_range": None,
    "charging_state": None,
    "charge_rate": None,
    "inside_temp": None,
    "outside_temp": None,
    "odometer": None,
}

# Gear値の変換テーブル
GEAR_MAP = {
    "ShiftStateD": "D",
    "ShiftStateR": "R",
    "ShiftStateP": "P",
    "ShiftStateN": "N",
    "ShiftStateInvalid": None,
}


def parse_telemetry_record(data: dict) -> dict | None:
    """Fleet Telemetryのdataフィールドをパースしてlatest_stateを更新。"""
    if "Vin" not in data:
        return None  # connectivityレコード等はスキップ

    updated = False

    # Location (lat/lon)
    if "Location" in data:
        loc = data["Location"]
        latest_state["latitude"] = loc.get("latitude")
        latest_state["longitude"] = loc.get("longitude")
        updated = True

    # Speed (mph → km/h)
    if "VehicleSpeed" in data:
        latest_state["speed"] = round(data["VehicleSpeed"] * 1.60934, 1)
        updated = True

    # GPS Heading
    if "GpsHeading" in data:
        latest_state["heading"] = data["GpsHeading"]
        updated = True

    # Gear / Shift State
    if "Gear" in data:
        latest_state["shift_state"] = GEAR_MAP.get(data["Gear"], data["Gear"])
        updated = True

    # Battery Level
    if "BatteryLevel" in data:
        latest_state["battery_level"] = int(round(data["BatteryLevel"]))
        updated = True

    # Battery Range (miles → km)
    if "EstBatteryRange" in data:
        latest_state["battery_range"] = round(data["EstBatteryRange"] * 1.60934, 1)
        updated = True

    # Charge State
    if "ChargeState" in data:
        latest_state["charging_state"] = data["ChargeState"]
        updated = True

    # Charge Rate
    if "ChargeRateMilePerHour" in data:
        latest_state["charge_rate"] = data["ChargeRateMilePerHour"]
        updated = True

    # Inside Temp
    if "InsideTemp" in data:
        latest_state["inside_temp"] = round(data["InsideTemp"], 1)
        updated = True

    # Outside Temp
    if "OutsideTemp" in data:
        latest_state["outside_temp"] = round(data["OutsideTemp"], 1)
        updated = True

    # Odometer (miles → km)
    if "Odometer" in data:
        latest_state["odometer"] = round(data["Odometer"] * 1.60934, 1)
        updated = True

    # Soc (same as BatteryLevel but sometimes sent separately)
    if "Soc" in data and "BatteryLevel" not in data:
        latest_state["battery_level"] = int(round(data["Soc"]))
        updated = True

    if not updated:
        return None

    # CreatedAtをタイムスタンプとして使う
    ts = data.get("CreatedAt", datetime.now(timezone.utc).isoformat())

    return {"timestamp": ts, **latest_state}


def insert_with_timestamp(row: dict) -> None:
    """タイムスタンプ付きでSQLiteに挿入。"""
    cols = [
        "timestamp", "latitude", "longitude", "speed", "heading",
        "shift_state", "power", "battery_level", "battery_range",
        "charging_state", "charge_rate", "inside_temp", "outside_temp",
        "odometer",
    ]
    vals = [row.get(c) for c in cols]
    placeholders = ", ".join("?" for _ in cols)
    col_names = ", ".join(cols)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            f"INSERT INTO vehicle_log ({col_names}) VALUES ({placeholders})",
            vals,
        )


def stream_logs():
    """SSH経由でVPSのjournaldログをリアルタイムにストリーム。"""
    cmd = [
        "ssh", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=5",
        "-o", "TCPKeepAlive=yes",
        "-o", "ConnectTimeout=10",
        f"{SSH_USER}@{VPS_HOST}",
        "sudo", "journalctl", "-u", "fleet-telemetry", "-f", "--no-pager",
        "-o", "cat",  # JSON部分のみ出力
    ]

    print(f"[bridge] VPS {VPS_HOST} に接続中...")
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    print(f"[bridge] 接続成功。テレメトリデータ待機中...")

    record_count = 0
    last_report = time.time()

    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        # record_payloadかつVデータ（車両データ）のみ処理
        if msg.get("msg") != "record_payload":
            continue

        metadata = msg.get("metadata", {})
        txtype = metadata.get("txtype")

        # Vタイプ（vehicle data）のみ
        if txtype != "V":
            # connectivity, alerts, errorsはログだけ出す
            if txtype:
                data = msg.get("data", {})
                if isinstance(data, dict):
                    status = data.get("Status", "")
                    network = data.get("NetworkInterface", "")
                    if status:
                        print(f"[bridge] {txtype}: {status} ({network})")
            continue

        data = msg.get("data", {})
        if not isinstance(data, dict):
            continue
        row = parse_telemetry_record(data)
        if row is None:
            continue

        insert_with_timestamp(row)
        record_count += 1

        # 状態表示（10秒ごと）
        now = time.time()
        if now - last_report >= 10:
            ts = row.get("timestamp", "?")
            bat = row.get("battery_level", "?")
            temp = row.get("inside_temp", "?")
            spd = row.get("speed", 0) or 0
            gear = row.get("shift_state", "?")
            print(
                f"[bridge] #{record_count} | {ts} | "
                f"🔋{bat}% | 🌡{temp}°C | "
                f"🚗{spd}km/h ({gear})"
            )
            last_report = now

    # プロセスが終了した場合
    rc = proc.wait()
    return rc


def main():
    init_db()
    print(f"[bridge] Tesla Fleet Telemetry Bridge")
    print(f"[bridge] DB: {DB_PATH}")
    print(f"[bridge] VPS: {VPS_HOST}")
    print()

    while True:
        try:
            rc = stream_logs()
            print(f"[bridge] SSH切断 (rc={rc})。10秒後に再接続...")
        except KeyboardInterrupt:
            print("\n[bridge] 停止")
            break
        except Exception as e:
            print(f"[bridge] エラー: {e}。10秒後に再接続...")

        time.sleep(10)


if __name__ == "__main__":
    main()
