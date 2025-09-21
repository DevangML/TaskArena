# TaskArena SaaS

TaskArena SaaS installs a background worker service that orchestrates Claude CLI plan/apply jobs for any repository on your machine. The service lives entirely under `~/.taskarena/`, exposes a local HTTP endpoint for job submission, and ships with a convenient `ta` CLI helper.

## Features

- **One-line installation** that provisions the service, CLI, agent rules, and background process.
- **Background job runner** (`systemd`, `launchd`, or `nohup` fallback) that persists across restarts.
- **Claude CLI plan-first execution** with automatic detection of `claude -p` support and safe fallback to `claude code plan/apply`.
- **Rule merging** that loads host project rules from `docs/rules.md` or `docs/rules/*.md` and layers on TaskArena agent guidance.
- **File-system queue** rooted at `~/.taskarena/queue/{inbox,running,done,failed}` for atomic worker claims.
- **Artifacts and logs** stored in `~/.taskarena/patches/<repo_key>/<job_id>/` and `~/.taskarena/logs/run.jsonl`.
- **Local CLI helper** (`~/.local/bin/ta`) that sends tasks to the daemon.

## Quick start

```bash
curl -fsSL https://raw.githubusercontent.com/DevangML/TaskArena/install.sh | bash
```

After installation the `ta` command is ready:

```bash
# Run from within a repository
ta . "Refactor the parser to stream tokens"

# Or target another path
ta ~/projects/app "Add README badges"
```

## Runtime layout

```
~/.taskarena/
  service.py              # Background HTTP + worker process
  queue/                  # inbox, running, done, failed
  logs/run.jsonl          # Append-only job log
  patches/<repo_key>/<id>/# Plan and apply artifacts per job
  rules/agents.md         # TaskArena additive rules
```

The daemon listens on `http://127.0.0.1:8787/jobs` and launches `TA_WORKERS` worker threads (default 4). Each worker:

1. Claims a JSON job file from the inbox via `os.replace` for atomic locking.
2. Loads combined rules (host first, TaskArena additive) and renders the planning template.
3. Runs the Claude CLI planning step, then the apply step, capturing stdout/stderr into artifacts.
4. Moves the job file to `done/` or `failed/` and appends a JSON line to the run log.

## Background service

- **Linux:** Installs `~/.config/systemd/user/taskarena.service` and enables it via `systemctl --user`.
- **macOS:** Creates `~/Library/LaunchAgents/com.taskarena.service.plist` and loads it with `launchctl`.
- **Other platforms:** Falls back to `nohup python3 ~/.taskarena/service.py &` with logs in `~/.taskarena/logs/`.

## Development

- `service.py` contains the HTTP server, queue, and worker implementation.
- `cli/ta` submits jobs to the local daemon.
- `rules/agents.md` documents TaskArena’s additive rules; host repositories keep control of their existing docs.
- `install.sh` bootstraps the environment when fetched via the published curl command.

Refer to the `docs/` folder for the fact sheet, goal, and acceptance criteria that guided this implementation.
