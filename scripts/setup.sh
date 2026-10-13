#!/usr/bin/env bash
# ScanMyLib — complete installation or update.
#
# Everything runs in Docker containers: nothing is installed on the system.
#   1. prepares .env and the folders (DATA_DIR, LIBRARY_DIR);
#   2. builds the `scanmylib-api` and `scanmylib-ocr` images;
#   3. installs the OCR sandbox (packages + models) with the `ocr-setup`
#      container, the only OCR container with network access, which only sees
#      SANDBOX_DIR;
#   4. builds the Android APK in a throwaway container (unless --no-apk);
#   5. starts the services and checks that the sandbox is isolated.
#
# Usage: scripts/setup.sh [--no-apk]
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)
BUILD_APK=1
[[ "${1:-}" == "--no-apk" ]] && BUILD_APK=0

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

# --- 1. Configuration -------------------------------------------------------
if [[ ! -f .env ]]; then
  say "Creating .env"
  lan_ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}')
  sed -e "s#/data/USER#/data/$USER#; s#/home/USER#$HOME#" \
      -e "s#^SCANMYLIB_UID=.*#SCANMYLIB_UID=$(id -u)#; s#^SCANMYLIB_GID=.*#SCANMYLIB_GID=$(id -g)#" \
      -e "s#^PUBLIC_URL=.*#PUBLIC_URL=http://${lan_ip:-127.0.0.1}:8765#" \
      .env.example > .env
  echo "Check the paths in $ROOT/.env, then run this script again if needed."
fi
set -a; source .env; set +a

say "Folders"
# Created here, before Docker would create missing bind-mount sources as root.
mkdir -p "$DATA_DIR"/{sandbox,run,ocr-cache,state,app,android,logs} "$LIBRARY_DIR"
echo "DATA_DIR=$DATA_DIR  LIBRARY_DIR=$LIBRARY_DIR  PUBLIC_URL=$PUBLIC_URL"

# --- 2. Images --------------------------------------------------------------
say "Building the Docker images"
docker compose build api ocr

# --- 3. OCR sandbox ---------------------------------------------------------
if [[ -f "$SANDBOX_DIR/MANIFEST.json" ]]; then
  say "OCR sandbox already installed ($SANDBOX_DIR/MANIFEST.json)"
else
  say "Installing the OCR sandbox (downloads: ~16 GB)"
  docker compose --profile setup run --rm ocr-setup
fi

# --- 4. Android APK ---------------------------------------------------------
if (( BUILD_APK )); then
  say "Building the Android app (throwaway container)"
  scripts/build-apk.sh
fi

# --- 5. Start ---------------------------------------------------------------
say "Starting the services"
docker compose up -d api ocr

for _ in $(seq 60); do
  curl -fsS "http://127.0.0.1:${API_PORT:-8765}/api/health" >/dev/null 2>&1 && break
  sleep 1
done

say "Checking that the sandbox is isolated"
scripts/verify-sandbox.sh

token=$(cat "$DATA_DIR/state/token" 2>/dev/null || true)
say "Ready"
echo "Web UI: http://localhost:${API_PORT:-8765}/#token=${token}"
echo "To pair the phone: open the \"Pairing\" tab of the web UI and follow its two steps."
