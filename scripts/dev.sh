#!/usr/bin/env bash
# Runs the development stack of this worktree (its .env comes from scripts/dev-env.sh). Never
# touches production: before anything, it checks what docker compose resolves for this stack and
# refuses any project, image, port or host path production owns, any host path outside the
# stack's own DATA_DIR and any service setting outside an allowlist (scripts/lib/stack.py). Use
# it instead of plain docker compose in a worktree.
#
# Usage: scripts/dev.sh up [--real-ocr]     build the api image and start api + the OCR service of
#                                           .env (OCR_SERVICE, ocr-fake by default); --real-ocr
#                                           starts the sandbox instead: a second OCR engine next
#                                           to production's, ~4.4 GB of VRAM while it works
#        scripts/dev.sh down                stop and remove the containers (data and images stay)
#        scripts/dev.sh status              containers, api health and the worktree they run from
#        scripts/dev.sh logs [service...]   follow the logs (api, ocr-fake, ocr)
#        scripts/dev.sh build [service...]  build the images (default: api; ocr for the sandbox)
#        scripts/dev.sh compose COMMAND...  any other docker compose command on this stack, e.g.
#                                           "compose exec api sh", among those that stay within it
#                                           (scripts/lib/stack.py, check-compose-command): no
#                                           global option (-p, -f...), no cp, export, commit, push,
#                                           pull or scale, no run -v/-p/--cap-add/--name..., no exec
#                                           --privileged, no build --ssh/--push, no config -o; up,
#                                           create, start and restart name their services, never
#                                           both ocr and ocr-fake (they serve the same socket)
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=lib/common.sh
source "$ROOT/scripts/lib/common.sh"

ENV_FILE=$ROOT/.env
usage() { sed -n '/^# Usage:/,/^set /{/^set /d;s/^# \{0,1\}//;p}' "${BASH_SOURCE[0]}" >&2; exit 2; }

command=${1:-}
(($#)) && shift
case $command in
    up | down | status | logs | build | compose) ;;
    *) usage ;;
esac

[[ -f $ENV_FILE ]] || die "no $ENV_FILE: run scripts/dev-env.sh first"
assert_isolated_from_production "$ENV_FILE"
load_env "$ENV_FILE" STACK
PROJECT=${STACK[COMPOSE_PROJECT_NAME]}
DATA_DIR=${STACK[DATA_DIR]}
LIBRARY_DIR=${STACK[LIBRARY_DIR]}
API_PORT=${STACK[API_PORT]:-8765}

# Where the containers of this project were started from, if they run.
running_from() {
    docker ps --filter "label=com.docker.compose.project=$PROJECT" \
        --format '{{.Label "com.docker.compose.project.working_dir"}}' | sort -u | paste -sd ' '
}

health() {
    curl -fsS --max-time 3 "http://127.0.0.1:$API_PORT/api/health" 2> /dev/null || true
}

# Created here, before Docker would create missing bind-mount sources as root.
make_directories() {
    mkdir -p "$DATA_DIR"/{state,run,ocr-cache,app,logs} "$LIBRARY_DIR"
}

build() {
    local service
    (($#)) || set -- api
    for service in "$@"; do
        [[ $service == api || $service == ocr ]] || die "only api and ocr are built, not '$service'"
    done
    [[ " $* " == *" ocr "* ]] && echo "The ocr image: the sandbox of scripts/dev.sh up --real-ocr."
    compose build "$@"
}

up() {
    local ocr_service other
    ocr_service=${STACK[OCR_SERVICE]:-ocr-fake}
    case ${1:-} in
        --real-ocr) ocr_service=ocr ;;
        "") ;;
        *) usage ;;
    esac
    [[ $ocr_service == ocr || $ocr_service == ocr-fake ]] || die "OCR_SERVICE must be ocr or ocr-fake"
    other=$([[ $ocr_service == ocr ]] && echo ocr-fake || echo ocr)

    local from
    from=$(running_from)
    if [[ -n $from && $from != "$ROOT" ]]; then
        echo "The $PROJECT stack runs from $from: replacing it with this worktree's."
    fi

    say "Building ($PROJECT)"
    make_directories
    if [[ $ocr_service == ocr ]]; then
        echo "The real OCR sandbox: a second engine next to production's (~4.4 GB of VRAM while it works)."
        build api ocr
    else
        build api
    fi

    say "Starting api and $ocr_service"
    # Both OCR services serve the same socket: never run them together.
    compose rm --stop --force "$other"
    compose up -d --wait --wait-timeout 180 api "$ocr_service"
    status
}

status() {
    compose ps -a
    local reply token
    reply=$(health)
    echo
    echo "api health: ${reply:-no answer on port $API_PORT}"
    echo "running from: $(running_from)"
    token=$(cat "$DATA_DIR/state/token" 2> /dev/null || true)
    if [[ -n $token ]]; then
        echo "web UI: http://localhost:$API_PORT/#token=$token"
        echo "phone: ${STACK[PUBLIC_URL]:-} (dev app: scripts/build-apk.sh, then the Pairing tab)"
    fi
}

case $command in
    up) up "$@" ;;
    down) (($# == 0)) || usage; compose down ;;
    status) (($# == 0)) || usage; status ;;
    logs) compose logs --follow --tail 200 "$@" ;;
    build) make_directories; build "$@" ;;
    compose)
        # A docker compose command first (options before it would be compose's global options,
        # -p, -f, --env-file..., which could point it at another stack), and only the commands and
        # options that stay within the stack.
        python3 "$SCRIPTS_LIB/stack.py" check-compose-command -- "$@" \
            || die "scripts/dev.sh compose COMMAND [ARGS...]: refused (see above); nothing was done"
        [[ $1 == up || $1 == run || $1 == create ]] && make_directories
        compose "$@"
        ;;
esac
