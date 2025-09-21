#!/usr/bin/env python3
"""TaskArena SaaS background service."""
from __future__ import annotations

import hashlib
import http.server
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional

STATE_DIR = Path.home() / ".taskarena"
QUEUE_DIR = STATE_DIR / "queue"
INBOX_DIR = QUEUE_DIR / "inbox"
RUNNING_DIR = QUEUE_DIR / "running"
DONE_DIR = QUEUE_DIR / "done"
FAILED_DIR = QUEUE_DIR / "failed"
LOG_FILE = STATE_DIR / "logs" / "run.jsonl"
PATCH_DIR = STATE_DIR / "patches"
RULES_FILE = STATE_DIR / "rules" / "agents.md"
WORKER_COUNT = max(int(os.environ.get("TA_WORKERS", "4")), 1)
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8787

_PLAN_TEMPLATE = """# TaskArena Planning Request

## Job ID
{job_id}

## Working Directory
{repo}

## Task Prompt
{prompt}

## Combined Rules (Host takes precedence)
{rules}

Produce a concise plan with:
- Key constraints from the rules.
- 3-5 ordered steps that respect repo safety.
- Risks or blockers.
- Acceptance checks aligned with the host project.
"""

_APPLY_TEMPLATE = """# TaskArena Apply Instructions

You are executing TaskArena job {job_id} in repository {repo}.

## Combined Rules (Host precedence)
{rules}

## Approved Plan
{plan}

## Task Prompt
{prompt}

Follow the approved plan. Explain the changes you make and ensure artifacts are generated.
"""

_LOG_LOCK = threading.Lock()
_QUEUE_LOCK = threading.Lock()
_SUPPORTS_CACHE: Optional[bool] = None
_CLAUDE_PATH: Optional[str] = None


def ensure_directories() -> None:
    for path in [STATE_DIR, QUEUE_DIR, INBOX_DIR, RUNNING_DIR, DONE_DIR, FAILED_DIR, PATCH_DIR, LOG_FILE.parent, RULES_FILE.parent]:
        path.mkdir(parents=True, exist_ok=True)
    LOG_FILE.touch(exist_ok=True)


def atomic_write_json(path: Path, payload: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def enqueue_job(job: dict) -> Path:
    ensure_directories()
    job_file = INBOX_DIR / f"{job['id']}.json"
    atomic_write_json(job_file, job)
    return job_file


def claim_job() -> Optional[Path]:
    ensure_directories()
    with _QUEUE_LOCK:
        for job_file in sorted(INBOX_DIR.glob("*.json")):
            target = RUNNING_DIR / job_file.name
            try:
                os.replace(job_file, target)
                return target
            except FileNotFoundError:
                continue
            except PermissionError:
                continue
    return None


def finish_job(job_file: Path, success: bool) -> None:
    target_dir = DONE_DIR if success else FAILED_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / job_file.name
    os.replace(job_file, target)


def compute_repo_key(repo: Path) -> str:
    slug = repo.name.strip().lower() or "project"
    slug = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in slug)
    digest = hashlib.sha256(str(repo).encode("utf-8")).hexdigest()[:8]
    slug = slug.strip("-") or "project"
    return f"{slug}-{digest}"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except Exception:
        return ""


def load_host_rules(repo: Path) -> str:
    rules_md = repo / "docs" / "rules.md"
    if rules_md.exists():
        return read_text(rules_md)
    rules_dir = repo / "docs" / "rules"
    if rules_dir.exists() and rules_dir.is_dir():
        chunks: list[str] = []
        for child in sorted(rules_dir.glob("*.md")):
            content = read_text(child)
            if content:
                chunks.append(content)
        return "\n\n".join(chunks)
    return ""


def combined_rules(repo: Path) -> str:
    host = load_host_rules(repo)
    agents = read_text(RULES_FILE)
    if host and agents:
        return "\n\n".join([host, "---", "# TaskArena Agent Rules", agents])
    return host or agents or "No additional rules available."


def _resolve_claude_cli() -> str:
    """Locate the Claude CLI executable, caching the discovered path."""

    global _CLAUDE_PATH
    if _CLAUDE_PATH:
        return _CLAUDE_PATH

    candidates: list[Path] = []

    override = os.environ.get("CLAUDE_CLI")
    if override:
        candidates.append(Path(override).expanduser())

    which_path = shutil.which("claude")
    if which_path:
        candidates.append(Path(which_path))

    candidates.append(Path.home() / ".local/bin/claude")

    seen: set[Path] = set()
    for candidate in candidates:
        if not candidate:
            continue
        resolved = candidate.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists() and os.access(resolved, os.X_OK):
            _CLAUDE_PATH = str(resolved)
            return _CLAUDE_PATH

    raise RuntimeError(
        "Claude CLI executable not found. Install the `claude` command, add it to your PATH, "
        "or set CLAUDE_CLI to its full path before starting TaskArena."
    )


def _detect_supports_dash_p() -> bool:
    global _SUPPORTS_CACHE
    if _SUPPORTS_CACHE is not None:
        return _SUPPORTS_CACHE
    try:
        claude_cli = _resolve_claude_cli()
        result = subprocess.run([claude_cli, "--help"], capture_output=True, text=True, timeout=10)
    except RuntimeError:
        raise
    except Exception:
        _SUPPORTS_CACHE = False
        return _SUPPORTS_CACHE
    help_text = (result.stdout or "") + (result.stderr or "")
    _SUPPORTS_CACHE = "-p" in help_text or "--prompt" in help_text
    return _SUPPORTS_CACHE


def _run_subprocess(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True)


def run_plan(repo: Path, prompt: str, job_id: str) -> tuple[subprocess.CompletedProcess[str], str]:
    rules_text = combined_rules(repo)
    plan_prompt = _PLAN_TEMPLATE.format(job_id=job_id, repo=str(repo), prompt=prompt, rules=rules_text)
    supports_dash = _detect_supports_dash_p()
    claude_cli = _resolve_claude_cli()
    if supports_dash:
        proc = _run_subprocess([claude_cli, "-p", plan_prompt])
        return proc, rules_text
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".md") as handle:
        handle.write(plan_prompt)
        handle.flush()
        temp_path = handle.name
    try:
        proc = _run_subprocess([claude_cli, "code", "plan", "--repo", str(repo), "--plan", temp_path])
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
    return proc, rules_text


def run_apply(repo: Path, prompt: str, job_id: str, rules_text: str, plan_output: str) -> subprocess.CompletedProcess[str]:
    approved_plan = plan_output.strip() or "Plan output missing."
    apply_prompt = _APPLY_TEMPLATE.format(job_id=job_id, repo=str(repo), rules=rules_text, plan=approved_plan, prompt=prompt)
    supports_dash = _detect_supports_dash_p()
    claude_cli = _resolve_claude_cli()
    if supports_dash:
        return _run_subprocess([claude_cli, "-p", apply_prompt])
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".md") as handle:
        handle.write(apply_prompt)
        handle.flush()
        temp_path = handle.name
    try:
        return _run_subprocess([claude_cli, "code", "apply", "--repo", str(repo), "--plan", temp_path])
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def log_event(entry: dict) -> None:
    entry.setdefault("ts", time.time())
    with _LOG_LOCK:
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def process_job(job_file: Path) -> None:
    raw = read_text(job_file)
    try:
        job = json.loads(raw)
    except json.JSONDecodeError:
        finish_job(job_file, False)
        log_event({"id": job_file.stem, "dir": None, "repo_key": None, "ok": False, "error": "Invalid job JSON"})
        return

    repo = Path(job.get("dir", ".")).expanduser()
    prompt = job.get("prompt", "").strip()
    repo_key = job.get("repo_key") or compute_repo_key(repo)
    job_id = job.get("id") or str(uuid.uuid4())
    artifact_dir = PATCH_DIR / repo_key / job_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    def write_artifact(name: str, content: str) -> None:
        (artifact_dir / name).write_text(content or "", encoding="utf-8")

    if not repo.exists() or not repo.is_dir():
        message = f"Repository path does not exist: {repo}"
        write_artifact("error.txt", message)
        finish_job(job_file, False)
        log_event({"id": job_id, "dir": str(repo), "repo_key": repo_key, "ok": False, "error": message})
        return
    if not prompt:
        message = "Empty prompt provided."
        write_artifact("error.txt", message)
        finish_job(job_file, False)
        log_event({"id": job_id, "dir": str(repo), "repo_key": repo_key, "ok": False, "error": message})
        return

    try:
        plan_proc, rules_text = run_plan(repo, prompt, job_id)
    except RuntimeError as exc:
        error_message = str(exc)
        write_artifact("stderr.txt", error_message)
        finish_job(job_file, False)
        log_event({"id": job_id, "dir": str(repo), "repo_key": repo_key, "ok": False, "error": error_message})
        return

    write_artifact("plan.stdout.txt", plan_proc.stdout or "")
    write_artifact("plan.stderr.txt", plan_proc.stderr or "")

    if plan_proc.returncode != 0:
        finish_job(job_file, False)
        log_event({"id": job_id, "dir": str(repo), "repo_key": repo_key, "ok": False, "error": "Plan step failed"})
        return

    apply_proc = run_apply(repo, prompt, job_id, rules_text, plan_proc.stdout or "")
    write_artifact("apply.stdout.txt", apply_proc.stdout or "")
    write_artifact("apply.stderr.txt", apply_proc.stderr or "")

    ok = apply_proc.returncode == 0
    finish_job(job_file, ok)
    log_event({"id": job_id, "dir": str(repo), "repo_key": repo_key, "ok": ok})


class Worker(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)

    def run(self) -> None:  # pragma: no cover
        while True:
            job_file = claim_job()
            if job_file is None:
                time.sleep(0.5)
                continue
            try:
                process_job(job_file)
            except Exception as exc:
                finish_job(job_file, False)
                log_event({"id": job_file.stem, "dir": None, "repo_key": None, "ok": False, "error": f"Worker exception: {exc}"})


class TaskArenaRequestHandler(http.server.BaseHTTPRequestHandler):
    server_version = "TaskArenaHTTP/1.0"

    def do_POST(self) -> None:  # pragma: no cover
        if self.path != "/jobs":
            self.send_error(404, "Endpoint not found")
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        data = self.rfile.read(length)
        try:
            payload = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON payload")
            return
        directory = payload.get("dir")
        prompt = (payload.get("prompt") or "").strip()
        if not directory or not prompt:
            self.send_error(400, "Both 'dir' and 'prompt' are required.")
            return
        repo = Path(directory).expanduser()
        if not repo.exists() or not repo.is_dir():
            self.send_error(400, f"Directory does not exist: {repo}")
            return
        job_id = str(uuid.uuid4())
        repo_key = compute_repo_key(repo)
        job = {"id": job_id, "dir": str(repo), "repo_key": repo_key, "prompt": prompt}
        enqueue_job(job)
        response = json.dumps({"id": job_id, "repo_key": repo_key}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args) -> None:  # pragma: no cover
        return


def start_workers() -> None:
    for _ in range(WORKER_COUNT):
        Worker().start()


def serve() -> None:
    ensure_directories()
    start_workers()
    httpd = http.server.ThreadingHTTPServer((SERVER_HOST, SERVER_PORT), TaskArenaRequestHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()
