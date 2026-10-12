#!/usr/bin/env bash
set -euo pipefail

# ラズパイ（pi0w）の作業ディレクトリ（~/myroom-api）へファイル一式をSCPでアップロードするスクリプト。
# WinSCPでの手動アップロードの代替。
#
# WSL2からは raspberrypi.local / 192.168.1.x に到達できないため、
# Windows PowerShell（Git Bash 等）や、LANに直接出られる環境で実行すること。
#
# 使い方:
#   ./deploy.sh              # ローカル/リモートの差分確認 → 確認プロンプト → 転送
#   ./deploy.sh --diff        # 差分確認のみ（転送しない）
#   ./deploy.sh --install     # 転送後、Pi上で sudo ./install.sh とタイマー再起動まで実行
#   ./deploy.sh --yes         # 確認プロンプトをスキップ
#   （フラグは組み合わせ可能。例: ./deploy.sh --install --yes）
#
# 接続先は環境変数で上書き可能:
#   PI_HOST=raspberrypi.local PI_USER=pi-user PI_SSH_KEY=~/.ssh/pi0w REMOTE_DIR=myroom-api ./deploy.sh

PI_HOST="${PI_HOST:-raspberrypi.local}"
PI_USER="${PI_USER:?Set PI_USER to the SSH login user}"
PI_SSH_KEY="${PI_SSH_KEY:-$HOME/.ssh/pi0w}"
REMOTE_DIR="${REMOTE_DIR:-myroom-api}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FILES=(
  switchbot_to_myroom.py
  aircon_to_myroom.py
  aircloudhome_client.py
  run-aircon-collector.sh
  requirements.txt
  install.sh
  sensors.json.example
  .env.example
)

SSH_OPTS=(-i "${PI_SSH_KEY}")
TARGET="${PI_USER}@${PI_HOST}"

DO_INSTALL=0
DIFF_ONLY=0
SKIP_CONFIRM=0

for arg in "$@"; do
  case "${arg}" in
    --install) DO_INSTALL=1 ;;
    --diff) DIFF_ONLY=1 ;;
    --yes|-y) SKIP_CONFIRM=1 ;;
    *)
      echo "不明なオプション: ${arg}" >&2
      exit 1
      ;;
  esac
done

check_diff() {
  DIFF_COUNT=0
  for f in "${FILES[@]}"; do
    local local_path="${SCRIPT_DIR}/${f}"
    local remote_path="${REMOTE_DIR}/${f}"
    if ssh "${SSH_OPTS[@]}" "${TARGET}" "test -f ${remote_path}" 2>/dev/null; then
      local d
      d="$(diff -u --label "remote:${f}" --label "local:${f}" \
        <(ssh "${SSH_OPTS[@]}" "${TARGET}" "cat ${remote_path}") "${local_path}" || true)"
      if [[ -n "${d}" ]]; then
        echo "----- ${f} -----"
        echo "${d}"
        DIFF_COUNT=$((DIFF_COUNT + 1))
      fi
    else
      echo "----- ${f}（新規ファイル・リモートに存在しません） -----"
      DIFF_COUNT=$((DIFF_COUNT + 1))
    fi
  done
}

echo "==> ${TARGET}:${REMOTE_DIR}/ との差分を確認しています..."
ssh "${SSH_OPTS[@]}" "${TARGET}" "mkdir -p ${REMOTE_DIR}"
check_diff

if [[ "${DIFF_COUNT}" -eq 0 ]]; then
  echo "==> 差分なし。アップロードは不要です"
  exit 0
fi

if [[ "${DIFF_ONLY}" -eq 1 ]]; then
  exit 0
fi

if [[ "${SKIP_CONFIRM}" -ne 1 ]]; then
  read -r -p "上記の差分をアップロードしますか？ (y/N) " confirm
  case "${confirm}" in
    y|Y|yes|YES) ;;
    *)
      echo "中止しました"
      exit 1
      ;;
  esac
fi

echo "==> ${TARGET}:${REMOTE_DIR}/ へ転送します"

SRC_FILES=()
for f in "${FILES[@]}"; do
  SRC_FILES+=("${SCRIPT_DIR}/${f}")
done

scp "${SSH_OPTS[@]}" "${SRC_FILES[@]}" "${TARGET}:${REMOTE_DIR}/"

echo "==> 転送完了"

if [[ "${DO_INSTALL}" -eq 1 ]]; then
  echo "==> Pi上で install.sh を実行し、タイマーを再起動します（sudoパスワードの入力を求められます）"
  ssh "${SSH_OPTS[@]}" -t "${TARGET}" \
    "cd ${REMOTE_DIR} && chmod +x install.sh run-aircon-collector.sh && sudo ./install.sh && sudo systemctl restart switchbot-co2.timer aircon-myroom.timer"
  echo "==> インストール・再起動完了"
fi


