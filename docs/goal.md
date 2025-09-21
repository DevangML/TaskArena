# Goal

Deliver a one-command installer that deploys TaskArena as a persistent background service using the Claude CLI only. The system must isolate all runtime state under `~/.taskarena/`, expose a lightweight local HTTP API, provide a CLI shim for submissions, and respect both host repository rules and TaskArena agent guidance during every plan/apply cycle.
