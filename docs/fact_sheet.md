# Fact Sheet

- **Service endpoint:** `http://127.0.0.1:8787/jobs` accepts JSON `{"dir","prompt"}` payloads.
- **Queue layout:** `~/.taskarena/queue/{inbox,running,done,failed}` with atomic `os.replace` for claims.
- **Artifacts:** `~/.taskarena/patches/<repo_key>/<job_id>/` holds `plan.stdout.txt`, `plan.stderr.txt`, `apply.stdout.txt`, `apply.stderr.txt`, and error notes.
- **Logs:** `~/.taskarena/logs/run.jsonl` appends `{"id","dir","repo_key","ok","ts"}` per job.
- **Rules merge:** host `docs/rules.md` or `docs/rules/*.md` + TaskArena `~/.taskarena/rules/agents.md` (host text wins on conflicts).
- **Workers:** `TA_WORKERS` (default 4) threads spawned by `service.py` perform plan then apply using Claude CLI.
- **CLI helper:** `~/.local/bin/ta` posts tasks to the service after verifying directory existence.
