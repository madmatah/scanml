#!/usr/bin/env bash
# Runs docker compose on production, for its operation (state, logs, restarts, a rollback): only
# in production's checkout (the project directory of production's containers, else
# ~/Dev/scanmylib: scripts/lib/stack.py), with production's .env and nothing else. Plain docker
# compose would also read the caller's environment (COMPOSE_*, DATA_DIR...), which overrides .env.
# Production changes through scripts/deploy.sh: builds, one-off containers, cp, push... are refused
# (scripts/lib/stack.py, check-compose-command), and so is the fake OCR. up applies this
# checkout's compose.yaml to production, so only on a release (HEAD is the commit of the tag
# vVERSION, as this checkout's tags say: deploy.sh checked it on origin), clean (untracked files
# included, and no file marked assume-unchanged or skip-worktree, as in scripts/deploy.sh), and
# never builds (--no-build is added): it starts the images scripts/deploy.sh built. start and
# restart restart the existing containers as they were created.
#
# Usage: scripts/prod.sh compose COMMAND [ARGS...]
#   e.g. scripts/prod.sh compose ps
#        scripts/prod.sh compose logs -f api ocr
#        scripts/prod.sh compose restart api
#        scripts/prod.sh compose up -d --no-build api ocr
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=lib/common.sh
source "$ROOT/scripts/lib/common.sh"

usage() {
    sed -n '/^# Usage:/,/^set /{/^set /d;s/^# \{0,1\}//;p}' "${BASH_SOURCE[0]}" >&2
    exit 2
}

[[ ${1:-} == compose ]] || usage
shift
python3 "$SCRIPTS_LIB/stack.py" check-compose-command --production -- "$@" \
    || die "scripts/prod.sh compose COMMAND [ARGS...]: refused (see above); nothing was done"

checkout=$(production_checkout) || die "cannot tell production's checkout (see above)"
is_production_checkout "$ROOT" "$checkout" \
    || die "$ROOT is not production's checkout ($checkout): in a worktree, use scripts/dev.sh"
[[ -f $ROOT/.env ]] || die "no $ROOT/.env: production's is written by scripts/setup.sh"
load_env "$ROOT/.env" STACK
[[ ${STACK[COMPOSE_PROJECT_NAME]:-} == "$PRODUCTION_PROJECT" ]] \
    || die "$ROOT/.env is not production's (COMPOSE_PROJECT_NAME=${STACK[COMPOSE_PROJECT_NAME]:-unset})"

case $1 in
    up)
        # What up applies is this checkout's compose.yaml: a release as committed, nothing else.
        # start and restart only restart the existing containers, as they were created.
        release_error=$(release_problem "$ROOT" local) || die "$release_error: nothing was done"
        [[ -z $(git -C "$ROOT" status --porcelain --untracked-files=all) ]] \
            || die "production's checkout has uncommitted or untracked changes (git status): nothing was done"
        hidden=$(hidden_changes "$ROOT")
        [[ -z $hidden ]] || die "files marked assume-unchanged or skip-worktree could hide changes: \
$(tr '\n' ' ' <<< "$hidden")(git update-index --no-assume-unchanged --no-skip-worktree FILE)"
        ;;
esac
# Production's images come from scripts/deploy.sh: never built here.
[[ $1 == up ]] && set -- up --no-build "${@:2}"

# Production's services only: never the fake OCR next to the sandbox.
# shellcheck disable=SC2034  # read by compose() of scripts/lib/common.sh
COMPOSE_PROFILE_ARGS=()
compose "$@"
