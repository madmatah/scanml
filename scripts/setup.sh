#!/usr/bin/env bash
# ScanMyLib — first installation of production, in production's checkout (~/Dev/scanmylib, as
# long as no production container names another: scripts/lib/stack.py), clean, on a published
# release (git checkout vX.Y.Z: HEAD is the commit of that tag on origin). Once production exists
# (its containers or its database), it refuses: new releases are deployed with scripts/deploy.sh,
# the only way production changes afterwards; a worktree runs the development stack instead
# (scripts/dev-env.sh, scripts/dev.sh).
#
# Everything runs in Docker containers: nothing is installed on the system.
#   1. writes .env from .env.example with production's identity (COMPOSE_PROJECT_NAME=scanmylib...),
#      unless it exists, and checks it (strict format of scripts/lib/stack.py: never sourced);
#   2. creates the folders (DATA_DIR, ANDROID_DIR, LIBRARY_DIR);
#   3. builds the `scanmylib-api` and `scanmylib-ocr` images;
#   4. installs the OCR sandbox (packages + models) with the `ocr-setup` container, the only OCR
#      container with network access, which only sees SANDBOX_SETUP_DIR;
#   5. creates the app's signing key and builds the APK in throwaway containers (unless --no-apk);
#   6. starts the services and checks that the sandbox is isolated.
#
# Usage: scripts/setup.sh [--no-apk]
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=lib/common.sh
source "$ROOT/scripts/lib/common.sh"
cd "$ROOT"

BUILD_APK=1
case ${1:-} in
    --no-apk) BUILD_APK=0 ;;
    "") ;;
    *)
        sed -n 's/^# Usage: //p' "${BASH_SOURCE[0]}" >&2
        exit 2
        ;;
esac

CHECKOUT=$(production_checkout) || die "cannot tell production's checkout (see above)"
if ! is_production_checkout "$ROOT" "$CHECKOUT"; then
    die "$ROOT is not production's checkout: scripts/setup.sh installs production, in $CHECKOUT.
For a development stack here: scripts/dev-env.sh, then scripts/dev.sh up."
fi
release_error=$(release_problem "$ROOT") || die "install a published release: $release_error"
[[ -z $(git status --porcelain --untracked-files=all) ]] || die "install from a clean checkout (git status)"
docker info --format '{{.ServerVersion}}' > /dev/null 2>&1 || die "cannot reach Docker"

# Production exists once its containers or its database do: deploy.sh takes over from there.
existing=$(docker ps --all --quiet --filter "label=com.docker.compose.project=$PRODUCTION_PROJECT")
[[ -z $existing ]] || die "production already exists (containers of the project $PRODUCTION_PROJECT): \
deploy new versions with scripts/deploy.sh"

# --- 1. Configuration -------------------------------------------------------
if [[ ! -f .env ]]; then
    say "Creating .env"
    lan_ip=$(ip -4 route get 1.1.1.1 2> /dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}')
    time_zone=$(timedatectl show --property=Timezone --value 2> /dev/null || cat /etc/timezone 2> /dev/null || true)
    [[ $time_zone =~ ^[A-Za-z0-9_+/-]+$ ]] || time_zone=UTC
    user=$(id -un)
    [[ $user =~ ^[A-Za-z0-9_.-]+$ && $HOME =~ ^/[A-Za-z0-9_./-]+$ ]] \
        || die "your user name or home path has characters a .env cannot hold: write .env from .env.example by hand"
    example=$(sed -e "s#/data/USER#/data/$user#; s#/home/USER#$HOME#" \
        -e "s#^SCANMYLIB_UID=.*#SCANMYLIB_UID=$(id -u)#; s#^SCANMYLIB_GID=.*#SCANMYLIB_GID=$(id -g)#" \
        -e "s#^PUBLIC_URL=.*#PUBLIC_URL=http://${lan_ip:-127.0.0.1}:8765#" \
        -e "s#^SCANMYLIB_TZ=.*#SCANMYLIB_TZ=$time_zone#" \
        .env.example)
    tmp=$(mktemp --suffix=.tmp "$ROOT/.env.XXXXXX")
    trap 'rm -f "$tmp"' EXIT
    {
        printf '%s\n\n' "$example"
        echo "# Production's identity, written by scripts/setup.sh (never in a worktree)."
        echo "COMPOSE_PROJECT_NAME=$PRODUCTION_PROJECT"
        echo "IMAGE_PREFIX=$PRODUCTION_PROJECT"
        echo "SANDBOX_SETUP_DIR=$(sed -n 's/^SANDBOX_DIR=//p' <<< "$example")"
        echo "OCR_SERVICE=ocr"
        echo "APP_VARIANT=release"
    } > "$tmp"
    python3 "$SCRIPTS_LIB/stack.py" env "$tmp" > /dev/null || die "the generated .env is invalid (see above)"
    chmod 644 "$tmp"
    mv "$tmp" .env
    trap - EXIT
    echo "Check the paths in $ROOT/.env, then run this script again if needed."
fi
load_env .env STACK
[[ ${STACK[COMPOSE_PROJECT_NAME]:-} == "$PRODUCTION_PROJECT" ]] \
    || die ".env is not production's (COMPOSE_PROJECT_NAME=${STACK[COMPOSE_PROJECT_NAME]:-unset}): \
remove it to have it written again from .env.example"
DATA_DIR=${STACK[DATA_DIR]:-}
LIBRARY_DIR=${STACK[LIBRARY_DIR]:-}
SANDBOX_DIR=${STACK[SANDBOX_DIR]:-}
ANDROID_DIR=${STACK[ANDROID_DIR]:-$DATA_DIR/android}
API_PORT=${STACK[API_PORT]:-8765}
for path in "$DATA_DIR" "$LIBRARY_DIR" "$SANDBOX_DIR" "$ANDROID_DIR"; do
    [[ $path == /* ]] || die "DATA_DIR, LIBRARY_DIR, SANDBOX_DIR and ANDROID_DIR must be absolute paths in .env"
done
[[ ${STACK[SANDBOX_SETUP_DIR]:-} == "$SANDBOX_DIR" ]] \
    || die "SANDBOX_SETUP_DIR must be SANDBOX_DIR ($SANDBOX_DIR) in production's .env"
[[ ! -e $DATA_DIR/state/scanmylib.db ]] \
    || die "production already exists ($DATA_DIR/state/scanmylib.db): deploy new versions with scripts/deploy.sh"

say "Folders"
# Created here, before Docker would create missing bind-mount sources as root.
mkdir -p "$DATA_DIR"/{run,ocr-cache,state,app,logs} "$SANDBOX_DIR" "$ANDROID_DIR" "$LIBRARY_DIR"
echo "DATA_DIR=$DATA_DIR  LIBRARY_DIR=$LIBRARY_DIR  PUBLIC_URL=${STACK[PUBLIC_URL]:-}"

# --- 2. Images --------------------------------------------------------------
say "Building the Docker images"
compose build api ocr

# --- 3. OCR sandbox ---------------------------------------------------------
if [[ -f $SANDBOX_DIR/MANIFEST.json ]]; then
    say "OCR sandbox already installed ($SANDBOX_DIR/MANIFEST.json)"
else
    say "Installing the OCR sandbox (downloads: ~16 GB)"
    compose --profile setup run --rm ocr-setup
fi

# --- 4. Android APK ---------------------------------------------------------
if ((BUILD_APK)); then
    say "Building the Android app (throwaway containers)"
    scripts/build-apk.sh --create-signing-key
fi

# --- 5. Start ---------------------------------------------------------------
say "Starting the services"
compose up -d --no-build --wait --wait-timeout 300 api ocr

say "Checking that the sandbox is isolated"
scripts/verify-sandbox.sh

token=$(cat "$DATA_DIR/state/token" 2> /dev/null || true)
say "Ready"
echo "Web UI: http://localhost:$API_PORT/#token=${token}"
echo "To pair the phone: open the \"Pairing\" tab of the web UI and follow its two steps."
echo "New versions: scripts/deploy.sh (see README.md, \"Deployment\")."
