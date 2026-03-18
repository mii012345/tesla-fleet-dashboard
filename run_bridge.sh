#!/bin/bash
cd /home/yuto/seeda-corp/experiments/tesla-dashboard
exec env PYTHONUNBUFFERED=1 \
  /home/yuto/seeda-corp/experiments/tesla-dashboard/venv/bin/python3 \
  telemetry_bridge.py
