#!/usr/bin/env python3
"""Tesla Dashboard — FastAPI backend."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from db import DB_PATH, get_latest, get_logs, get_trips, get_charging_sessions

app = FastAPI(title="Tesla Dashboard")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api/latest")
def api_latest():
    row = get_latest()
    return row or {"error": "no data"}


@app.get("/api/logs")
def api_logs(
    since: str = Query(default=None, description="ISO timestamp or relative like '24h', '7d'"),
    until: str = Query(default=None),
):
    since_ts = _parse_since(since, default_hours=24)
    return get_logs(since=since_ts, until=until)


@app.get("/api/trips")
def api_trips(
    since: str = Query(default=None),
):
    since_ts = _parse_since(since, default_hours=168)  # 7 days
    return get_trips(since=since_ts)


@app.get("/api/charging")
def api_charging(
    since: str = Query(default=None),
):
    since_ts = _parse_since(since, default_hours=168)
    return get_charging_sessions(since=since_ts)


def _parse_since(value: str | None, default_hours: int = 24) -> str:
    """Parse relative time ('24h', '7d') or ISO timestamp."""
    if value is None:
        dt = datetime.now(timezone.utc) - timedelta(hours=default_hours)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if value.endswith("h"):
        hours = int(value[:-1])
        dt = datetime.now(timezone.utc) - timedelta(hours=hours)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if value.endswith("d"):
        days = int(value[:-1])
        dt = datetime.now(timezone.utc) - timedelta(days=days)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return value  # assume ISO


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
