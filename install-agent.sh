#!/usr/bin/env bash
set -euo pipefail

# install-agent.sh
# Usage: sudo bash install-agent.sh <ORCH_URL> [--no-bootstrap]
# Example:
#   curl -fsSL https://orchestrator.example.com/install-agent.sh | sudo bash -s -- https://orchestrator.example.com

ORCH_URL="${1:-}"
NO_BOOTSTRAP_FLAG="${2:-}"
if [ -z "$ORCH_URL" ]; then
  echo "Usage: sudo $0 <ORCH_URL> [--no-bootstrap]"
  exit 2
fi

AGENT_DIR="/opt/deploy-agent"
VENV_DIR="$AGENT_DIR/venv"
AGENT_SCRIPT_URL="$ORCH_URL/files/agent.py"
BOOTSTRAP_URL="$ORCH_URL/files/bootstrap_vps.sh"
AGENT_SCRIPT_PATH="$AGENT_DIR/agent-vps.py"
BOOTSTRAP_PATH="$AGENT_DIR/bootstrap_vps.sh"
SYSTEMD_UNIT="/etc/systemd/system/deploy-agent.service"

echo "[install-agent] ORCH_URL = $ORCH_URL"
echo "[install-agent] AGENT_DIR = $AGENT_DIR"

# ensure running as root
if [ "$(id -u)" -ne 0 ]; then
  echo "This installer must be run as root (sudo)."
  exit 1
fi

mkdir -p "$AGENT_DIR"
chown root:root "$AGENT_DIR"
chmod 755 "$AGENT_DIR"

echo "[install-agent] Downloading agent script from $AGENT_SCRIPT_URL ..."
# curl -fsS  "$AGENT_SCRIPT_URL" -o "$AGENT_SCRIPT_PATH"
chmod 750 "$AGENT_SCRIPT_PATH"

echo "[install-agent] Downloading bootstrap script from $BOOTSTRAP_URL ..."
# curl -fsSL "$BOOTSTRAP_URL" -o "$BOOTSTRAP_PATH"
chmod 750 "$BOOTSTRAP_PATH"

echo "[install-agent] Creating python venv for agent..."

apt update && apt install python3.12-venv -y

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install requests fastapi uvicorn

echo "[install-agent] Creating systemd service..."
cat > "$SYSTEMD_UNIT" <<EOF
[Unit]
Description=Deploy Agent
After=network.target

[Service]
User=root
ExecStart=$VENV_DIR/bin/python $AGENT_SCRIPT_PATH
Restart=always
RestartSec=5
Environment=ORCH_URL=$ORCH_URL

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now deploy-agent.service

echo "[install-agent] Service deploy-agent started."

# Run bootstrap unless --no-bootstrap is passed
if [ "$NO_BOOTSTRAP_FLAG" = "--no-bootstrap" ]; then
  echo "[install-agent] Skipping bootstrap (user requested --no-bootstrap)."
else
  echo "[install-agent] Running bootstrap to prepare VPS (may take several minutes)..."
  # run the bootstrap script with environment variables set
  bash "$BOOTSTRAP_PATH"
  echo "[install-agent] Bootstrap finished."
fi

echo "Installation complete. Check status: sudo journalctl -u deploy-agent.service -f"
