#!/bin/bash
# Flask on :5000 and JupyterLab on :8888. Extra arguments go to JupyterLab.
# If either one stops, stop the other and exit non-zero so the lab is reported as failed instead of half working.
set -u

flask_host="${FLASK_HOST:-0.0.0.0}"
jupyter_host="${JUPYTER_HOST:-0.0.0.0}"

flask --app app run --host "$flask_host" --port 5000 --reload --no-debugger &
flask_pid=$!

jupyter lab --ip "$jupyter_host" --port 8888 --no-browser \
  --ServerApp.token= --ServerApp.password= --ServerApp.allow_remote_access=True "$@" &
jupyter_pid=$!

trap 'kill "$flask_pid" "$jupyter_pid" 2>/dev/null; wait; exit 0' INT TERM

wait -n "$flask_pid" "$jupyter_pid"
status=$?
echo "start-lab: a lab service stopped (exit $status), stopping the lab" >&2
kill "$flask_pid" "$jupyter_pid" 2>/dev/null
wait
exit $(( status == 0 ? 1 : status ))
