import os, json, time, uuid, shutil, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / ".agents"
INBOX = ROOT/"queue/inbox"
RUNNING = ROOT/"queue/running"
DONE = ROOT/"queue/done"
FAILED = ROOT/"failed" if (ROOT/"failed").exists() else ROOT/"queue/failed"
PATCHES = ROOT/"patches"
LOG_FILE = ROOT/"logs"/"run.jsonl"
SCORE_FILE = ROOT/"scores"/"scoreboard.json"
AGENTS_RULES = ROOT/"docs"/"rules.agents.md"


def claude_available() -> bool:
    """Return True when the Claude CLI binary is discoverable on PATH."""
    return shutil.which("claude") is not None

def ensure_dirs():
    for p in [INBOX, RUNNING, DONE, FAILED, PATCHES, LOG_FILE.parent, SCORE_FILE.parent]:
        p.mkdir(parents=True, exist_ok=True)

def logj(obj):
    ensure_dirs()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False)+"\n")

def atomic_write_json(path: Path, data: dict):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.rename(path)

def enqueue(prompt: str, repo: str, mode: str = "code_apply", hint: str | None = None):
    ensure_dirs()
    tid = str(uuid.uuid4())
    task = {"id": tid, "mode": mode, "prompt": prompt, "repo": repo}
    if hint: task["hint"] = hint
    dst = INBOX / f"{tid}.json"
    atomic_write_json(dst, task)
    return tid, dst

def claim():
    ensure_dirs()
    for p in sorted(INBOX.glob("*.json")):
        try:
            tgt = RUNNING/p.name
            p.rename(tgt)  # atomic claim
            return tgt
        except Exception:
            continue
    return None

def finish(tpath: Path, ok: bool):
    dst = (DONE if ok else FAILED) / tpath.name
    tpath.rename(dst)
    return dst

def _cli_supports_dash_p() -> bool:
    if not claude_available():
        return False
    try:
        out = subprocess.run(["claude","--help"], capture_output=True, text=True, timeout=15)
        return ("-p" in out.stdout) or ("--prompt" in out.stdout)
    except Exception:
        return False

def claude_plan_apply(repo: Path, plan_md: str, apply_md: str):
    """
    Plan then apply using Claude CLI only.
    Prefer `claude -p` if available, else `claude code plan/apply`.
    """
    if not claude_available():
        raise FileNotFoundError(
            "Claude CLI ('claude') not found on PATH. Install the claude binary to run workers."
        )
    def run(args, input_text=None):
        return subprocess.run(args, input=input_text, capture_output=True, text=True, timeout=600)

    if _cli_supports_dash_p():
        p1 = run(["claude","-p", plan_md])
        p2 = run(["claude","-p", apply_md])
        rc = p2.returncode
        out = (p1.stdout or "") + "\n---\n" + (p2.stdout or "")
        err = (p1.stderr or "") + "\n---\n" + (p2.stderr or "")
        return rc, out, err
    else:
        with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as f1:
            f1.write(plan_md); f1.flush()
            p_plan = run(["claude","code","plan","--repo", str(repo), "--plan", f1.name])
        with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as f2:
            f2.write(apply_md); f2.flush()
            p_apply = run(["claude","code","apply","--repo", str(repo), "--plan", f2.name])
        rc = p_apply.returncode
        out = (p_plan.stdout or "") + "\n---\n" + (p_apply.stdout or "")
        err = (p_plan.stderr or "") + "\n---\n" + (p_apply.stderr or "")
        return rc, out, err

def read_file(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""

def load_host_rules(repo_root: Path) -> str:
    # Prefer docs/rules.md; else concatenate any docs/rules/*.md
    rules_file = repo_root/"docs"/"rules.md"
    if rules_file.exists():
        return rules_file.read_text(encoding="utf-8")
    rules_dir = repo_root/"docs"/"rules"
    if rules_dir.exists():
        parts = []
        for f in sorted(rules_dir.glob("*.md")):
            parts.append(f"\n\n# {f.stem}\n\n"+read_file(f))
        return "".join(parts)
    return ""

def combined_rules(repo_root: Path) -> str:
    host = load_host_rules(repo_root)
    agents = read_file(AGENTS_RULES)
    if host and agents:
        return host + "\n\n<!-- BEGIN: agents-fs-cli rules -->\n" + agents + "\n<!-- END: agents-fs-cli rules -->\n"
    if agents: return agents
    return host
