#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AG="$ROOT/.agents"
Q="$AG/queue"
export PYTHONPATH="$AG/tools:${PYTHONPATH:-}"
mkdir -p "$Q/inbox" "$Q/running" "$Q/done" "$Q/failed" "$AG/logs" "$AG/patches" "$AG/scores" "$AG/scratch"

banner() {
  printf "\n==== Multi-Agent Arena (Claude CLI) ====\n"
  printf "1) Show combined rules (host + agents)\n"
  printf "2) Enqueue task\n"
  printf "3) Run workers (parallel)\n"
  printf "4) Run judge\n"
  printf "5) Tail logs\n"
  printf "6) Exit\n"
}

show_rules() {
  python3 - <<'PY'
from pathlib import Path
from util import combined_rules
repo = Path('.').resolve()
txt = combined_rules(repo)
print(txt if txt.strip() else "No rules found.")
PY
}

enqueue() {
  echo "Task prompt (end with Ctrl+D):"
  PROMPT=$(cat)
  python3 "$AG/tools/router.py" <<<"$PROMPT"
  echo "Enqueued."
}

workers() {
  read -rp "How many workers? [4]: " N; N=${N:-4}
  seq 1 "$N" | xargs -I{} -n1 -P"$N" python3 "$AG/tools/worker.py" &
  echo "Workers running."
}

judge() { python3 "$AG/tools/judge.py" & echo "Judge running."; }
logs() { touch "$AG/logs/run.jsonl"; tail -n 200 -f "$AG/logs/run.jsonl"; }

while true; do
  banner
  read -rp "> " c
  case "$c" in
    1) show_rules;;
    2) enqueue;;
    3) workers;;
    4) judge;;
    5) logs;;
    6) exit 0;;
    *) echo "Invalid";;
  esac
done
