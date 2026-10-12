#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/room-panel}"
SERVICE_NAME="room-panel"
SERVICE_USER="panel"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo ./install.sh"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing to ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"
cp "${SCRIPT_DIR}"/*.py "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/web" "${INSTALL_DIR}/"

# 作業ディレクトリの .env を優先（無ければ .env.example）。既存の.envは上書きしない
_env_source="${SCRIPT_DIR}/.env"
if [[ ! -f "${_env_source}" ]]; then
  _env_source="${SCRIPT_DIR}/.env.example"
fi
if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
  cp "${_env_source}" "${INSTALL_DIR}/.env"
  echo "Created ${INSTALL_DIR}/.env from $(basename "${_env_source}")."
else
  echo "Keeping existing ${INSTALL_DIR}/.env"
fi

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --home "${INSTALL_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}"
fi
usermod -aG i2c,gpio "${SERVICE_USER}" || true

# I2Cの有効化を試行（既に有効な場合は何もしない）。未確認: raspi-config nonint の戻り値仕様は
# Raspberry Pi OSのバージョンにより差異がある可能性があるため、失敗しても処理は継続する
if command -v raspi-config >/dev/null 2>&1; then
  raspi-config nonint do_i2c 0 || echo "raspi-config でのI2C有効化に失敗しました。手動で 'sudo raspi-config' から Interface Options > I2C を有効化してください（要再起動）。"
fi

python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Room status LCD/LED panel + Web UI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/app.py
Restart=on-failure
RestartSec=5
Nice=10

[Install]
WantedBy=multi-user.target
EOF

chmod 600 "${INSTALL_DIR}/.env"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"

echo
echo "Installed."
echo
echo "1. I2Cを初めて有効化した場合は再起動してください: sudo reboot"
echo "2. .envを編集: sudo nano ${INSTALL_DIR}/.env"
echo "   (MYROOM_API_TOKEN / UPTIME_KUMA_BASE_URL / UPTIME_KUMA_SLUG / LED*_PIN 等)"
echo "3. LCDアドレス確認: i2cdetect -y ${LCD_I2C_PORT:-1}"
echo "4. 疎通確認: sudo ${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/app.py --check-myroom"
echo "             sudo ${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/app.py --check-uptime-kuma"
echo "5. 起動: sudo systemctl start ${SERVICE_NAME}.service"
echo "6. ログ: journalctl -u ${SERVICE_NAME}.service -f"

