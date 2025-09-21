#!/usr/bin/env python3
import json, time
from pathlib import Path
from util import (
    PATCHES,
    claude_available,
    claude_plan_apply,
    claim,
    combined_rules,
    finish,
    logj,
)

PLAN_PROMPT_PATH = Path(__file__).with_name("plan_prompt.md")
PLAN_BASE = PLAN_PROMPT_PATH.read_text(encoding="utf-8") if PLAN_PROMPT_PATH.exists() else ""


def build_plan_prompt(rules: str) -> str:
    rules_section = rules.strip() if rules and rules.strip() else "_No additional rules found._"
    return f"{PLAN_BASE}\n\n## Constraints and Risks\n{rules_section}"

def run_once():
    tpath = claim()
    if not tpath:
        time.sleep(0.2); return
    task = json.loads(tpath.read_text())
    t0 = time.time()
    ok = False
    out = ""
    err = ""
    try:
        repo_root = Path(task.get("repo",".")).resolve()
        rules = combined_rules(repo_root)
        plan_md = build_plan_prompt(rules)
        apply_md = task["prompt"]
        if not claude_available():
            err = "Claude CLI ('claude') not found on PATH. Install the claude CLI to process tasks."
        else:
            rc, out, err = claude_plan_apply(repo_root, plan_md, apply_md)
            ok = (rc == 0)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        ok = False
    ap = PATCHES/task["id"]
    ap.mkdir(parents=True, exist_ok=True)
    (ap/"stdout.txt").write_text(out)
    (ap/"stderr.txt").write_text(err)
    finish(tpath, ok)
    logj({"id": task["id"], "ok": ok, "latency_s": round(time.time()-t0, 3)})

if __name__ == "__main__":
    while True:
        run_once()
