#!/usr/bin/env bash
set -euo pipefail

# ラズパイ（pi0w）の作業ディレクトリ（~/room-panel）へファイル一式をSCPでアップロードするスクリプト。
# WinSCPでの手動アップロードの代替。
#
# WSL2からは raspberrypi.local / 192.168.1.x に到達できないため、
# Windows PowerShell（Git Bash 等）や、LANに直接出られる環境で実行すること。
#
# 使い方:
#   ./deploy.sh              # ローカル/リモートの差分確認 → 確認プロンプト → 転送
#   ./deploy.sh --diff        # 差分確認のみ（転送しない）
#   ./deploy.sh --install     # 転送後、Pi上で sudo ./install.sh とサービス再起動まで実行
#   ./deploy.sh --yes         # 確認プロンプトをスキップ
#   （フラグは組み合わせ可能。例: ./deploy.sh --install --yes）
#
# 接続先は環境変数で上書き可能:
#   PI_HOST=raspberrypi.local PI_USER=pi-user PI_SSH_KEY=~/.ssh/pi0w REMOTE_DIR=room-panel ./deploy.sh
#
# venv/ .env/ dev.sh/ __pycache__ は開発専用・機密・生成物のためアップロード対象から除外する。

PI_HOST="${PI_HOST:-raspberrypi.local}"
PI_USER="${PI_USER:?Set PI_USER to the SSH login user}"
PI_SSH_KEY="${PI_SSH_KEY:-$HOME/.ssh/pi0w}"
REMOTE_DIR="${REMOTE_DIR:-room-panel}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SSH_OPTS=(-i "${PI_SSH_KEY}")
TARGET="${PI_USER}@${PI_HOST}"

# アップロード対象ファイルは web/ 以下のサブディレクトリも含めて実行時に自動収集する
# （install.sh がコピーする *.py / requirements.txt / web/ 一式 に .env.example・README.md を加えたもの）
mapfile -t FILES < <(cd "${SCRIPT_DIR}" && find . \
  -path './venv' -prune -o \
  -name '__pycache__' -prune -o \
  -name '.env' -prune -o \
  -name 'dev.sh' -prune -o \
  -name '.git' -prune -o \
  -type f -print | sed 's|^\./||' | sort)

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

# リモート側にサブディレクトリ（web/, web/static, web/templates 等）を先に作成しておく
REMOTE_SUBDIRS=()
for f in "${FILES[@]}"; do
  d="$(dirname "${f}")"
  if [[ "${d}" != "." ]]; then
    REMOTE_SUBDIRS+=("${REMOTE_DIR}/${d}")
  fi
done
if [[ "${#REMOTE_SUBDIRS[@]}" -gt 0 ]]; then
  mapfile -t UNIQUE_SUBDIRS < <(printf '%s\n' "${REMOTE_SUBDIRS[@]}" | sort -u)
  ssh "${SSH_OPTS[@]}" "${TARGET}" "mkdir -p ${UNIQUE_SUBDIRS[*]}"
fi

for f in "${FILES[@]}"; do
  scp "${SSH_OPTS[@]}" "${SCRIPT_DIR}/${f}" "${TARGET}:${REMOTE_DIR}/${f}"
done

echo "==> 転送完了"

if [[ "${DO_INSTALL}" -eq 1 ]]; then
  echo "==> Pi上で install.sh を実行し、サービスを再起動します（sudoパスワードの入力を求められます）"
  ssh "${SSH_OPTS[@]}" -t "${TARGET}" \
    "cd ${REMOTE_DIR} && chmod +x install.sh && sudo ./install.sh && sudo systemctl restart room-panel.service"
  echo "==> インストール・再起動完了"
fi


