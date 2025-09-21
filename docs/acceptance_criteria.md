# Acceptance Criteria

- `curl -fsSL https://raw.githubusercontent.com/<YOUR_GH_USER>/taskarena-saas/main/install.sh | bash` installs the service, CLI, rules, and background process without manual edits.
- The daemon keeps running across reboots via `systemd` (Linux), `launchd` (macOS), or a `nohup` fallback, always writing to `~/.taskarena/`.
- Submitting a job with `ta . "Prompt"` enqueues a JSON file in the inbox and returns `{"id","repo_key"}`.
- Each job executes `plan` before `apply`, captures stdout/stderr into `~/.taskarena/patches/<repo_key>/<job_id>/`, and logs an entry in `logs/run.jsonl`.
- Host `docs/rules.md` or `docs/rules/*.md` content is preserved and prepended to TaskArena rules for planning.
- Jobs from different repositories write to separate `patches/<repo_key>/` folders to avoid collision.
