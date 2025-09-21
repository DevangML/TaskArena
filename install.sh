
#!/usr/bin/env bash
set -euo pipefail

BASE_URL="https://raw.githubusercontent.com/<YOUR_GH_USER>/taskarena-saas/main"
STATE_DIR="${HOME}/.taskarena"
BIN_DIR="${HOME}/.local/bin"
QUEUE_DIRS=("queue/inbox" "queue/running" "queue/done" "queue/failed")
LOG_DIR="logs"
PATCH_DIR="patches"
RULES_DIR="rules"
SERVICE_PATH="${STATE_DIR}/service.py"
RULES_PATH="${STATE_DIR}/${RULES_DIR}/agents.md"
CLI_PATH="${BIN_DIR}/ta"
SYSTEM="$(uname -s)"

mkdir -p "${STATE_DIR}" "${BIN_DIR}"
for sub in "${QUEUE_DIRS[@]}" "${LOG_DIR}" "${PATCH_DIR}" "${RULES_DIR}"; do
  mkdir -p "${STATE_DIR}/${sub}"
done

fetch() {
  local src="$1"
  local dst="$2"
  curl -fsSL "${BASE_URL}/${src}" -o "${dst}"
}

fetch "service.py" "${SERVICE_PATH}"
fetch "rules/agents.md" "${RULES_PATH}"
fetch "cli/ta" "${CLI_PATH}"
chmod +x "${SERVICE_PATH}" "${CLI_PATH}"

start_nohup() {
  local log_out="${STATE_DIR}/logs/service.out.log"
  local log_err="${STATE_DIR}/logs/service.err.log"
  nohup python3 "${SERVICE_PATH}" >"${log_out}" 2>"${log_err}" &
  echo "[taskarena] Started service with nohup (PID $!)."
}

setup_systemd() {
  local unit_dir="${HOME}/.config/systemd/user"
  mkdir -p "${unit_dir}"
  local unit_file="${unit_dir}/taskarena.service"
  cat <<UNIT > "${unit_file}"
[Unit]
Description=TaskArena SaaS Background Service
After=network.target

[Service]
Type=simple
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/env python3 ${SERVICE_PATH}
Restart=always

[Install]
WantedBy=default.target
UNIT
  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload || true
    if ! systemctl --user enable --now taskarena.service; then
      echo "[taskarena] systemd enable/start failed; falling back to nohup."
      start_nohup
    fi
  else
    echo "[taskarena] systemctl not available; falling back to nohup startup."
    start_nohup
  fi
}

setup_launchd() {
  local launch_dir="${HOME}/Library/LaunchAgents"
  mkdir -p "${launch_dir}"
  local plist="${launch_dir}/com.taskarena.service.plist"
  cat <<PLIST > "${plist}"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.taskarena.service</string>
    <key>ProgramArguments</key>
    <array>
      <string>/usr/bin/env</string>
      <string>python3</string>
      <string>${SERVICE_PATH}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${STATE_DIR}/logs/service.out.log</string>
    <key>StandardErrorPath</key>
    <string>${STATE_DIR}/logs/service.err.log</string>
  </dict>
</plist>
PLIST
  if ! launchctl load -w "${plist}"; then
    echo "[taskarena] launchctl load failed; falling back to nohup."
    start_nohup
  fi
}

case "${SYSTEM}" in
  Linux)
    if command -v systemctl >/dev/null 2>&1; then
      setup_systemd
    else
      start_nohup
    fi
    ;;
  Darwin)
    setup_launchd
    ;;
  *)
    start_nohup
    ;;
esac

if ! command -v ta >/dev/null 2>&1; then
  if ! grep -qs "${BIN_DIR}" "${HOME}/.profile" 2>/dev/null; then
    printf 'export PATH="%s:$PATH"\n' "${BIN_DIR}" >> "${HOME}/.profile"
    echo "[taskarena] Added ${BIN_DIR} to PATH via ~/.profile. Restart your shell to use 'ta'."
  else
    echo "[taskarena] Add ${BIN_DIR} to PATH to use 'ta'."
  fi
fi

echo "[taskarena] Installation complete."
echo "[taskarena] Submit a job with: ta . \"Refactor parser\""
