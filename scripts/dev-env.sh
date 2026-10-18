#!/usr/bin/env bash
# Writes the .env of this worktree for the development stack: the single development slot that
# runs next to production, one at a time, from any worktree (see CLAUDE.md).
#
#   COMPOSE_PROJECT_NAME=scanmylib-dev   containers scanmylib-dev-*, images scanmylib-dev-api/-ocr
#   API_PORT=8770                        web UI and phone API (production: 8765)
#   DATA_DIR=<production DATA_DIR>-dev   its own state, socket, caches, APK, logs and a test library
#                                        (LIBRARY_DIR=$DATA_DIR/library), never the user's library
#   ANDROID_DIR=$DATA_DIR/android        its own Android SDK, Gradle caches and Android home, which
#                                        the first scripts/build-apk.sh downloads (and verifies)
#   SANDBOX_DIR                          production's OCR venvs and models, mounted read-only
#   ANDROID_KEYSTORE_DIR                 production's signing key, mounted read-only by the signing
#                                        container only (never by a build)
#   OCR_SERVICE=ocr-fake                 canned OCR results (scripts/dev.sh up --real-ocr: the sandbox)
#   APP_VARIANT=dev                      scripts/build-apk.sh builds "ScanMyLib (dev)", fr.scanmylib.dev
#   PUBLIC_URL=http://<LAN IP>:8770      what the dev app on the phone connects to
#
# Refuses to run in production's checkout (scripts/lib/stack.py) and to overwrite a .env that is
# not a development one; other settings of an existing development .env (OCR_IDLE_UNLOAD_S...)
# are kept. Production's paths come from the .env of production's checkout. The result must pass
# the isolation check of scripts/dev.sh. Next: scripts/dev.sh up.
#
# Usage: scripts/dev-env.sh
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=lib/common.sh
source "$ROOT/scripts/lib/common.sh"

(($# == 0)) || die "usage: scripts/dev-env.sh (no arguments)"

PRODUCTION_CHECKOUT=$(production_checkout) || exit 1
if is_production_checkout "$ROOT" "$PRODUCTION_CHECKOUT"; then
    die "$ROOT is production's checkout, where .env is production's: run this in a worktree (see CLAUDE.md)"
fi

ENV_FILE=$ROOT/.env
current=
if [[ -e $ENV_FILE ]]; then
    current=$(python3 "$SCRIPTS_LIB/stack.py" env "$ENV_FILE") \
        || die "refusing to overwrite $ENV_FILE, which is not a valid .env (see above): fix or remove it"
    [[ $(sed -n 's/^COMPOSE_PROJECT_NAME=//p' <<< "$current") == "$DEV_PROJECT" ]] \
        || die "refusing to overwrite $ENV_FILE: its COMPOSE_PROJECT_NAME is not $DEV_PROJECT"
fi

# Production's paths, from the .env of production's checkout (else the defaults of .env.example).
declare -A PRODUCTION=()
[[ -f $PRODUCTION_CHECKOUT/.env ]] && load_env "$PRODUCTION_CHECKOUT/.env" PRODUCTION
production_data=${PRODUCTION[DATA_DIR]:-/data/$(id -un)/scanmylib}
[[ $production_data == /* ]] || die "DATA_DIR in $PRODUCTION_CHECKOUT/.env must be an absolute path"
sandbox_dir=${PRODUCTION[SANDBOX_DIR]:-$production_data/sandbox}
production_android=${PRODUCTION[ANDROID_DIR]:-$production_data/android}
keystore_dir=${PRODUCTION[ANDROID_KEYSTORE_DIR]:-$production_android/keystore}
data_dir=$(realpath -m -- "$production_data")-dev
library_dir=$data_dir/library

# The port: free, or already published by the development stack itself.
foreign=$(docker ps --filter "publish=$DEV_API_PORT" --format '{{.Label "com.docker.compose.project"}}|{{.Names}}' \
    | awk -F'|' -v dev="$DEV_PROJECT" '$1 != dev {print $2}')
[[ -z $foreign ]] || die "port $DEV_API_PORT is published by other containers: $(tr '\n' ' ' <<< "$foreign")"
own=$(docker ps -q --filter "publish=$DEV_API_PORT" --filter "label=com.docker.compose.project=$DEV_PROJECT")
if [[ -z $own && -n $(ss -Hltn "sport = :$DEV_API_PORT" 2> /dev/null) ]]; then
    die "port $DEV_API_PORT is already in use on this PC (ss -ltn 'sport = :$DEV_API_PORT')"
fi
running_from=$(docker ps --filter "label=com.docker.compose.project=$DEV_PROJECT" \
    --format '{{.Label "com.docker.compose.project.working_dir"}}' | sort -u)

lan_ip=$(ip -4 route get 1.1.1.1 2> /dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}')

say "Development environment"
managed=(COMPOSE_PROJECT_NAME IMAGE_PREFIX SCANMYLIB_UID SCANMYLIB_GID DATA_DIR SANDBOX_DIR ANDROID_DIR
    ANDROID_KEYSTORE_DIR LIBRARY_DIR API_PORT PUBLIC_URL OCR_SERVICE APP_VARIANT)
managed_pattern="^($(
    IFS='|'
    echo "${managed[*]}"
))="
kept=()
while IFS= read -r line; do
    [[ -n $line && ! $line =~ $managed_pattern ]] && kept+=("$line")
done <<< "$current"

tmp=$(mktemp --suffix=.tmp "$ROOT/.env.XXXXXX")
trap 'rm -f "$tmp"' EXIT
{
    echo "# Development stack, written by scripts/dev-env.sh: run it again rather than editing these"
    echo "# lines (other settings are kept). Never point this file at production's data or library."
    echo "# Format: KEY=VALUE lines, values without spaces, quotes or comments (see .env.example)."
    echo "COMPOSE_PROJECT_NAME=$DEV_PROJECT"
    echo "IMAGE_PREFIX=$DEV_PROJECT"
    echo "SCANMYLIB_UID=$(id -u)"
    echo "SCANMYLIB_GID=$(id -g)"
    echo "DATA_DIR=$data_dir"
    echo "# Production's OCR venvs and models: mounted read-only."
    echo "SANDBOX_DIR=$sandbox_dir"
    echo "# The development slot's own Android SDK, Gradle caches and Android home."
    echo "ANDROID_DIR=$data_dir/android"
    echo "# Production's signing key: mounted read-only, by the signing container only."
    echo "ANDROID_KEYSTORE_DIR=$keystore_dir"
    echo "# A test library: never the user's."
    echo "LIBRARY_DIR=$library_dir"
    echo "API_PORT=$DEV_API_PORT"
    echo "PUBLIC_URL=http://${lan_ip:-127.0.0.1}:$DEV_API_PORT"
    echo "OCR_SERVICE=ocr-fake"
    echo "APP_VARIANT=dev"
    if ((${#kept[@]})); then
        echo "# Kept from the previous .env."
        printf '%s\n' "${kept[@]}"
    fi
} > "$tmp"
# The result must not share anything with production, as docker compose resolves it.
assert_isolated_from_production "$tmp"
mkdir -p "$data_dir"/{state,run,ocr-cache,app,logs} "$library_dir"
chmod 644 "$tmp"
mv -f "$tmp" "$ENV_FILE"
trap - EXIT

echo "Wrote $ENV_FILE:"
sed 's/^/  /' "$ENV_FILE"
if [[ -n $running_from && $running_from != "$ROOT" ]]; then
    echo
    echo "The development stack currently runs from $running_from: scripts/dev.sh up replaces it with this worktree's."
fi
echo
echo "Next: scripts/dev.sh up (fake OCR) or scripts/dev.sh up --real-ocr; the dev app: scripts/build-apk.sh."
