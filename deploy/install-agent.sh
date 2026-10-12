#!/usr/bin/env bash
set -euo pipefail
# Explicit local Pi administrator setup. Does not bootstrap or deploy an application.
[[ "$(id -u)" == 0 ]] || { echo 'Run this installer with sudo on the Pi'; exit 1; }
[[ "${1:-}" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo 'Usage: sudo bash deploy/install-agent.sh SSH_LOGIN_USER PUBLIC_KEY_FILE'; exit 1; }
id "$1" >/dev/null
[[ -f "${2:-}" ]] || { echo 'Second argument: reviewed deployment public key file'; exit 1; }
task_key=$(cat "$2")
[[ "$task_key" =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+(\ .*)?$ && "$task_key" != *$'\n'* ]] || { echo 'Expected one Ed25519 public key'; exit 1; }
task_home=$(getent passwd "$1" | cut -d: -f6)
[[ -d "$task_home" ]] || { echo 'SSH user must have an existing home'; exit 1; }
[[ ! -L "$task_home/.ssh" && ! -L "$task_home/.ssh/authorized_keys" ]] || { echo 'Refusing symlinked SSH paths'; exit 1; }
task_key_fields=$(printf '%s\n' "$task_key" | cut -d' ' -f1,2)
task_authorized="restrict,command=\"/usr/bin/sudo -n /usr/local/sbin/pi0w-deploy\" $task_key"
# Never quietly reuse an existing unrestricted key for deployment.
if [[ -f "$task_home/.ssh/authorized_keys" ]] && awk -v key="$task_key_fields" 'index($0,key) {found=1} END {exit !found}' "$task_home/.ssh/authorized_keys"; then
  if ! awk -v expected="$task_authorized" '$0 == expected {found=1} END {exit !found}' "$task_home/.ssh/authorized_keys"; then
    echo 'Key already exists with different restrictions; use a new dedicated key'
    exit 1
  fi
fi
cd "$(dirname "${BASH_SOURCE[0]}")"
# Allow this root-owned helper with NO command-line arguments, not general sudo/systemctl.
task_sudoers=$(mktemp)
trap 'rm -f "$task_sudoers"' EXIT
printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/pi0w-deploy ""\n' "$1" > "$task_sudoers"
visudo -cf "$task_sudoers" >/dev/null
install -o root -g root -m 0755 pi_agent.py /usr/local/sbin/pi0w-deploy
if [[ ! -e /etc/pi0w-deploy.json ]]; then
  install -o root -g root -m 0600 pi-config.example.json /etc/pi0w-deploy.json
fi
install -o root -g root -m 0440 "$task_sudoers" /etc/sudoers.d/pi0w-deploy
install -d -o "$1" -m 0700 "$task_home/.ssh"
touch "$task_home/.ssh/authorized_keys"
if ! awk -v key="$task_key_fields" 'index($0,key) {found=1} END {exit !found}' "$task_home/.ssh/authorized_keys"; then
  printf '%s\n' "$task_authorized" >> "$task_home/.ssh/authorized_keys"
fi
chown "$1" "$task_home/.ssh/authorized_keys"
chmod 0600 "$task_home/.ssh/authorized_keys"
printf 'Helper installed; inspect config, SSH trust and existing services before bootstrap.\n'

