# Agents Rules (Additive)
1) Only Claude CLI. No API keys or network calls.
2) No external infra. Files + git only.
3) Always run a **planning step** before apply.
4) Never overwrite code without saving artifacts in `.agents/patches/<task-id>/`.
5) Log every run to `.agents/logs/run.jsonl`.
6) Exit cleanly on Ctrl+C.
7) When conflicts exist, **host rules take precedence**; agents rules remain additive.
