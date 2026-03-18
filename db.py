"""SQLite schema & queries for Tesla driving log."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "driving_log.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicle_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    latitude        REAL,
    longitude       REAL,
    speed           REAL,
    heading         REAL,
    shift_state     TEXT,
    power           REAL,
    battery_level   INTEGER,
    battery_range   REAL,
    charging_state  TEXT,
    charge_rate     REAL,
    inside_temp     REAL,
    outside_temp    REAL,
    odometer        REAL
);
CREATE INDEX IF NOT EXISTS idx_log_ts ON vehicle_log(timestamp);
"""


def init_db(path: Path = DB_PATH) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)


def insert_log(row: dict, path: Path = DB_PATH) -> None:
    cols = [
        "latitude", "longitude", "speed", "heading", "shift_state",
        "power", "battery_level", "battery_range", "charging_state",
        "charge_rate", "inside_temp", "outside_temp", "odometer",
    ]
    vals = [row.get(c) for c in cols]
    placeholders = ", ".join("?" for _ in cols)
    col_names = ", ".join(cols)
    with sqlite3.connect(path) as conn:
        conn.execute(f"INSERT INTO vehicle_log ({col_names}) VALUES ({placeholders})", vals)


def _rows_to_dicts(cursor) -> list[dict]:
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def get_latest(path: Path = DB_PATH) -> dict | None:
    with sqlite3.connect(path) as conn:
        cur = conn.execute("SELECT * FROM vehicle_log ORDER BY id DESC LIMIT 1")
        rows = _rows_to_dicts(cur)
        return rows[0] if rows else None


def get_logs(since: str | None = None, until: str | None = None,
             path: Path = DB_PATH) -> list[dict]:
    """Time range query. since/until are ISO strings."""
    query = "SELECT * FROM vehicle_log WHERE 1=1"
    params = []
    if since:
        query += " AND timestamp >= ?"
        params.append(since)
    if until:
        query += " AND timestamp <= ?"
        params.append(until)
    query += " ORDER BY timestamp"
    with sqlite3.connect(path) as conn:
        return _rows_to_dicts(conn.execute(query, params))


def get_trips(since: str | None = None, min_pause_s: int = 120,
              path: Path = DB_PATH) -> list[dict]:
    """Detect trips from log data. A trip = contiguous non-P driving."""
    logs = get_logs(since=since, path=path)
    if not logs:
        return []

    trips = []
    current_trip = None

    for row in logs:
        shift = row.get("shift_state")
        if shift in ("D", "R", "N"):
            if current_trip is None:
                current_trip = {
                    "start_time": row["timestamp"],
                    "start_battery": row.get("battery_level"),
                    "start_odometer": row.get("odometer"),
                    "points": [],
                }
            current_trip["points"].append(row)
        elif shift == "P" or shift is None:
            if current_trip and len(current_trip["points"]) >= 2:
                last = current_trip["points"][-1]
                current_trip["end_time"] = last["timestamp"]
                current_trip["end_battery"] = last.get("battery_level")
                current_trip["end_odometer"] = last.get("odometer")
                trips.append(current_trip)
            current_trip = None

    # Close open trip
    if current_trip and len(current_trip["points"]) >= 2:
        last = current_trip["points"][-1]
        current_trip["end_time"] = last["timestamp"]
        current_trip["end_battery"] = last.get("battery_level")
        current_trip["end_odometer"] = last.get("odometer")
        trips.append(current_trip)

    return trips


def get_charging_sessions(since: str | None = None,
                          path: Path = DB_PATH) -> list[dict]:
    """Get charging data points."""
    query = "SELECT * FROM vehicle_log WHERE charging_state = 'Charging'"
    params = []
    if since:
        query += " AND timestamp >= ?"
        params.append(since)
    query += " ORDER BY timestamp"
    with sqlite3.connect(path) as conn:
        return _rows_to_dicts(conn.execute(query, params))
