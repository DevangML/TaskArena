#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(pwd)"
DEST="$REPO_ROOT/.agents"
BASE_URL="https://raw.githubusercontent.com/<YOUR_GH_USER>/agents-fs-cli/main/.agents"

mkdir -p "$DEST/queue/inbox" "$DEST/queue/running" "$DEST/queue/done" "$DEST/queue/failed" \
         "$DEST/scratch" "$DEST/patches" "$DEST/logs" "$DEST/scores" "$DEST/tools" "$DEST/docs"

# Fetch payload
for f in tools/util.py tools/router.py tools/worker.py tools/judge.py tools/menu.sh tools/plan_prompt.md Makefile docs/rules.agents.md; do
  curl -fsSL "$BASE_URL/$f" -o "$DEST/$f"
done

chmod +x "$DEST/tools/menu.sh" "$DEST/tools/router.py" "$DEST/tools/worker.py" "$DEST/tools/judge.py"

# Safe merge of host rules
if [ -f "$REPO_ROOT/docs/rules.md" ]; then
  cp "$REPO_ROOT/docs/rules.md" "$REPO_ROOT/docs/rules.pre-agents.md"
  if ! grep -q "BEGIN: agents-fs-cli rules" "$REPO_ROOT/docs/rules.md"; then
    {
      echo ""
      echo "<!-- BEGIN: agents-fs-cli rules -->"
      cat "$DEST/docs/rules.agents.md"
      echo "<!-- END: agents-fs-cli rules -->"
    } >> "$REPO_ROOT/docs/rules.md"
  fi
elif [ -d "$REPO_ROOT/docs/rules" ]; then
  # Do not modify individual files; place ours as a new file
  mkdir -p "$REPO_ROOT/docs/rules"
  cp "$DEST/docs/rules.agents.md" "$REPO_ROOT/docs/rules/agents-fs-cli.md"
else
  # Create new docs/rules.md with our section
  mkdir -p "$REPO_ROOT/docs"
  {
    echo "# Rules"
    echo "<!-- BEGIN: agents-fs-cli rules -->"
    cat "$DEST/docs/rules.agents.md"
    echo "<!-- END: agents-fs-cli rules -->"
  } > "$REPO_ROOT/docs/rules.md"
fi

echo "Installed .agents/ into $REPO_ROOT"
echo "Run: bash .agents/tools/menu.sh"
