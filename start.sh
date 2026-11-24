#!/usr/bin/env bash
set -e

uvicorn app.main:app --host 0.0.0.0 --port 8000 &
streamlit run dashboard/app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false &

wait -n
exit $?
