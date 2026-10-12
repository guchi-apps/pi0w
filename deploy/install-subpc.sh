#!/usr/bin/env bash
set -euo pipefail
# Installs user units only. Configuration, trust and bootstrap must already be reviewed.
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[[ -f "$HOME/.config/pi0w-deploy/config.json" ]] || { echo 'Create the private config first (docs/deployment.md)'; exit 1; }
[[ -f "$HOME/.local/state/pi0w-deploy/initialized" ]] || { echo 'Run a successful manual poll before enabling the timer'; exit 1; }
python3 deploy/controller.py status
mkdir -p "$HOME/.config/systemd/user"
install -m 0644 deploy/systemd/pi0w-deploy.service deploy/systemd/pi0w-deploy.timer "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now pi0w-deploy.timer

