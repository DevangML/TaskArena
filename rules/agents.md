# TaskArena Agent Rules

1. Only interact with Claude via the official Claude CLI. No API tokens or HTTP calls.
2. Keep all TaskArena state within `~/.taskarena/`. Never write to arbitrary global locations.
3. Always execute a planning step before attempting to apply changes.
4. Preserve host repository rules located in `docs/rules.md` or `docs/rules/*.md`; host instructions take precedence.
5. Emit artifacts for every job under `~/.taskarena/patches/<repo_key>/<job_id>/`.
6. Append an entry to `~/.taskarena/logs/run.jsonl` for every job with timing and success metadata.
7. Fail gracefully when prerequisites such as the Claude CLI are missing.
