#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  echo "[taskarena] python3 is required to run the progress viewer." >&2
  exit 1
fi

python3 - "$@" <<'PY'
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

STATE_DIR = Path.home() / ".taskarena"
QUEUE_DIR = STATE_DIR / "queue"
PATCH_DIR = STATE_DIR / "patches"
LOG_FILE = STATE_DIR / "logs" / "run.jsonl"

QUEUE_ORDER = [
    ("queued", QUEUE_DIR / "inbox"),
    ("running", QUEUE_DIR / "running"),
    ("done", QUEUE_DIR / "done"),
    ("failed", QUEUE_DIR / "failed"),
]


class ChatPrinter:
    COLORS = {
        "queued": "\033[36m",
        "running": "\033[35m",
        "done": "\033[32m",
        "failed": "\033[31m",
        "Coordinator": "\033[34m",
        "Planner": "\033[36m",
        "Applier": "\033[32m",
        "Log": "\033[33m",
        "Error": "\033[31m",
    }

    RESET = "\033[0m"

    def __init__(self, use_color: bool) -> None:
        self.use_color = use_color and sys.stdout.isatty()

    def _colorize(self, role: str, label: str) -> str:
        if not self.use_color:
            return label
        color = self.COLORS.get(role)
        if not color:
            return label
        return f"{color}{label}{self.RESET}"

    def emit(self, role: str, message: str, kind: Optional[str] = None) -> None:
        clean_message = message.rstrip()
        if not clean_message:
            clean_message = ""
        label_text = f"{role}:"
        plain_indent = " " * (len(label_text) + 1)
        label = self._colorize(kind or role, label_text)
        lines = clean_message.splitlines() or [""]
        print()
        print(f"{label} {lines[0] if lines else ''}")
        for line in lines[1:]:
            print(f"{plain_indent}{line}")
        print()


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize TaskArena job progress as a CLI chat stream",
    )
    parser.add_argument("job_id", help="TaskArena job identifier to watch")
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Polling interval in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors in chat output",
    )
    return parser.parse_args(list(argv))


def locate_job_file(job_id: str) -> Tuple[Optional[str], Optional[Path]]:
    for status, directory in QUEUE_ORDER:
        candidate = directory / f"{job_id}.json"
        if candidate.exists():
            return status, candidate
    return None, None


def load_job_manifest(job_path: Path) -> Optional[dict]:
    try:
        return json.loads(job_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_artifact_dir(job_id: str, repo_key: Optional[str]) -> Optional[Path]:
    if PATCH_DIR.exists():
        if repo_key:
            candidate = PATCH_DIR / repo_key / job_id
            if candidate.exists():
                return candidate
        for repo_dir in PATCH_DIR.iterdir():
            candidate = repo_dir / job_id
            if candidate.exists():
                return candidate
    return None


def load_log_entry(job_id: str) -> Optional[dict]:
    if not LOG_FILE.exists():
        return None
    entry: Optional[dict] = None
    try:
        with LOG_FILE.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    payload = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if payload.get("id") == job_id:
                    entry = payload
    except Exception:
        return None
    return entry


def render_artifact(
    printer: ChatPrinter,
    artifact_dir: Path,
    seen: Dict[str, str],
    filename: str,
    role: str,
    kind: Optional[str] = None,
) -> None:
    path = artifact_dir / filename
    if not path.exists():
        return
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return
    normalized = content.strip()
    if not normalized:
        return
    key = f"{role}:{filename}"
    if seen.get(key) == normalized:
        return
    seen[key] = normalized
    printer.emit(role, normalized, kind or role)


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    job_id: str = args.job_id
    interval: float = max(args.interval, 0.1)

    if not STATE_DIR.exists():
        print("[taskarena] No TaskArena state directory found.", file=sys.stderr)
        return 1

    printer = ChatPrinter(use_color=not args.no_color)
    printer.emit("Coordinator", f"Watching TaskArena job {job_id}")

    last_status: Optional[str] = None
    job_path: Optional[Path] = None
    manifest: Optional[dict] = None
    repo_key: Optional[str] = None
    artifact_dir: Optional[Path] = None
    seen_messages: Dict[str, str] = {}
    log_reported = False
    manifest_announced = False

    while True:
        status, candidate = locate_job_file(job_id)
        if candidate and candidate != job_path:
            job_path = candidate
            manifest = load_job_manifest(candidate)
            if manifest:
                repo_key = manifest.get("repo_key") or repo_key
                if not manifest_announced:
                    prompt = manifest.get("prompt", "(prompt unavailable)")
                    repo = manifest.get("dir", "(dir unknown)")
                    printer.emit(
                        "Coordinator",
                        f"Prompt: {prompt}\nRepository: {repo}",
                    )
                    manifest_announced = True
        if status and status != last_status:
            printer.emit("Coordinator", f"Job moved to {status.upper()} queue.", status)
            last_status = status
        if not artifact_dir:
            artifact_dir = find_artifact_dir(job_id, repo_key)
            if artifact_dir:
                printer.emit("Coordinator", f"Streaming artifacts from {artifact_dir}")
        if artifact_dir:
            render_artifact(printer, artifact_dir, seen_messages, "plan.stdout.txt", "Planner")
            render_artifact(printer, artifact_dir, seen_messages, "plan.stderr.txt", "Planner", kind="failed")
            render_artifact(printer, artifact_dir, seen_messages, "apply.stdout.txt", "Applier")
            render_artifact(printer, artifact_dir, seen_messages, "apply.stderr.txt", "Applier", kind="failed")
            render_artifact(printer, artifact_dir, seen_messages, "error.txt", "Error", kind="failed")
            render_artifact(printer, artifact_dir, seen_messages, "stderr.txt", "Error", kind="failed")
        if last_status in {"done", "failed"} and not log_reported:
            log_entry = load_log_entry(job_id)
            if log_entry:
                if log_entry.get("ok"):
                    printer.emit("Log", "Job completed successfully.", "done")
                else:
                    error_message = log_entry.get("error") or "Job finished with errors."
                    printer.emit("Log", error_message, "failed")
                log_reported = True
        if last_status in {"done", "failed"} and log_reported:
            break
        time.sleep(interval)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
PY
