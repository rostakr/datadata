#!/usr/bin/env bash
set -euo pipefail

PID_FILE="/tmp/datadata-streamlit.pid"
LOG_FILE="/tmp/datadata-streamlit.log"
PORT="${STREAMLIT_PORT:-8501}"

if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    echo "datadata Streamlit already running (pid=$pid, port=$PORT)."
    exit 0
  fi
  rm -f "$PID_FILE"
fi

nohup python -m streamlit run app.py \
  --server.address 0.0.0.0 \
  --server.port "$PORT" \
  --server.headless true \
  --browser.gatherUsageStats false \
  >"$LOG_FILE" 2>&1 &
pid=$!
echo "$pid" > "$PID_FILE"

for attempt in $(seq 1 30); do
  if curl --fail --silent "http://127.0.0.1:${PORT}/_stcore/health" >/dev/null; then
    echo "datadata Streamlit ready on port $PORT (pid=$pid)."
    exit 0
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    break
  fi
  sleep 1
done

cat "$LOG_FILE" >&2 || true
exit 1
