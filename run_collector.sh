#!/bin/bash
cd /home/yuto/seeda-corp/experiments/tesla-dashboard

set -a
source .env
set +a

if [ -f tesla_tokens.json ]; then
    export TESLA_ACCESS_TOKEN=$(python3 -c "import json; print(json.load(open('tesla_tokens.json'))['access_token'])")
    export TESLA_REFRESH_TOKEN=$(python3 -c "import json; print(json.load(open('tesla_tokens.json'))['refresh_token'])")
fi

exec /home/yuto/seeda-corp/experiments/tesla-dashboard/venv/bin/python3 collector.py
