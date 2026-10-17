# Shared by the scripts of scripts/ (sourced, not run).
#
# A stack is described by the .env of the checkout it runs from: production is production's
# checkout (the project directory of its containers, else ~/Dev/scanmylib; scripts/lib/stack.py)
# with its .env (COMPOSE_PROJECT_NAME=scanmylib, written by scripts/setup.sh), a worktree gets the
# development stack from scripts/dev-env.sh. The scripts read their settings from that .env only,
# in the strict format of scripts/lib/stack.py (load_env), and run docker compose with nothing but
# that .env (compose): the caller's environment never changes the stack.
#
# These checks protect production from misconfiguration, mistakes in a branch and compromised
# build dependencies; they do not claim to stop a deliberately malicious branch, whose scripts run
# as the user (docs/SECURITY.md).

# shellcheck disable=SC2034  # used by the scripts that source this file
readonly PRODUCTION_PROJECT=scanmylib
readonly DEV_PROJECT=scanmylib-dev
readonly DEV_API_PORT=8770
SCRIPTS_LIB=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
readonly SCRIPTS_LIB

# Variables a script could otherwise pick up from the caller's environment by mistake: the stack's
# settings come from .env (load_env), never from these.
readonly STACK_VARIABLES=(
    COMPOSE_PROJECT_NAME IMAGE_PREFIX SCANMYLIB_UID SCANMYLIB_GID DATA_DIR SANDBOX_DIR SANDBOX_SETUP_DIR
    ANDROID_DIR ANDROID_KEYSTORE_DIR LIBRARY_DIR API_PORT PUBLIC_URL OCR_SERVICE APP_VARIANT SCANMYLIB_TZ
    OCR_ENGINE OCR_BACKEND OCR_IDLE_UNLOAD_S OCR_VLLM_GPU_MEM OCR_VLLM_PORT OCR_MAX_CONCURRENCY
)
# And those of compose() below, which only the scripts set.
unset "${STACK_VARIABLES[@]}" COMPOSE_ROOT STACK_COMPOSE_FILE STACK_ENV_FILE

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# load_env FILE NAME: checks that FILE keeps to the strict .env format (scripts/lib/stack.py) and
# loads its KEY=VALUE lines into the global associative array NAME. Dies on any format error.
load_env() {
    local file=$1 lines line
    declare -gA "$2"
    local -n _values=$2
    _values=()
    lines=$(python3 "$SCRIPTS_LIB/stack.py" env "$file") || exit 1
    while IFS= read -r line; do
        if [[ -n $line ]]; then _values[${line%%=*}]=${line#*=}; fi
    done <<< "$lines"
}

# Production's checkout: the project directory of production's containers, else ~/Dev/scanmylib
# (scripts/lib/stack.py). Fails when Docker cannot be reached.
production_checkout() {
    local containers
    containers=$(production_containers) || {
        echo "cannot list production's containers: is Docker running?" >&2
        return 1
    }
    python3 "$SCRIPTS_LIB/stack.py" production-checkout <<< "$containers"
}

is_production_checkout() {  # is_production_checkout DIR CHECKOUT
    [[ "$(cd -- "$1" && pwd -P)" == "$(realpath -m -- "$2")" ]]
}

# Tracked files that git status does not compare with HEAD (assume-unchanged or skip-worktree):
# their changes would go unnoticed.
hidden_changes() {  # hidden_changes DIR
    git -C "$1" ls-files -v | sed -n 's/^[a-zS] //p'
}

# Production runs published releases only (.claude/rules/releases.md): HEAD must be the commit of the
# tag vVERSION, VERSION being HEAD's, as published on origin (git ls-remote), or with "local" as
# this checkout's tags say. Prints why not, and fails.
release_problem() {  # release_problem DIR [local]
    local dir=$1 version tag head named
    version=$(git -C "$dir" show HEAD:VERSION 2> /dev/null | tr -d '[:space:]' || true)
    if [[ ! $version =~ ^[0-9]{1,3}\.[0-9]{1,2}\.[0-9]{1,2}$ ]]; then
        echo "VERSION must be MAJOR.MINOR.PATCH (minor and patch below 100), not '$version'"
        return 1
    fi
    tag=v$version
    head=$(git -C "$dir" rev-parse HEAD)
    if [[ ${2:-} == local ]]; then
        named=$(git -C "$dir" rev-parse --verify --quiet "refs/tags/$tag^{commit}" || true)
    elif ! named=$(git -C "$dir" ls-remote --tags origin "refs/tags/$tag" "refs/tags/$tag^{}" \
        | sort -k 2 | tail -n 1 | cut -f 1); then
        echo "cannot read the tags of origin (git ls-remote --tags origin)"
        return 1
    fi
    if [[ -z $named && ${2:-} == local ]]; then
        echo "no tag $tag in this checkout: check out a published release (git fetch --tags origin, then git \
checkout vX.Y.Z)"
        return 1
    elif [[ -z $named ]]; then
        echo "$tag is not published on origin: its release workflow publishes it once the release pull request is \
merged; check out a published release (git fetch --tags origin, then git checkout vX.Y.Z)"
        return 1
    fi
    if [[ $named != "$head" ]]; then
        echo "HEAD ${head:0:12} is not the release $tag (${named:0:12}): production runs releases only (git checkout $tag, \
or a later release)"
        return 1
    fi
}

# docker compose on the stack of ROOT (set by the calling script), configured by its .env only
# (STACK_ENV_FILE, default ROOT/.env): COMPOSE_*, the stack's variables and anything else in the
# caller's environment never reach it. COMPOSE_ROOT replaces ROOT as the project directory (the
# build contexts, and the compose file), e.g. an export of the committed files; STACK_COMPOSE_FILE
# replaces the compose file only (default COMPOSE_ROOT/compose.yaml). COMPOSE_PROFILE_ARGS are the
# profiles: the fake OCR (ocr-fake) by default, none for scripts/prod.sh.
COMPOSE_PROFILE_ARGS=(--profile fake-ocr)
compose() {
    local name keep=()
    for name in HOME PATH LANG LC_ALL TERM NO_COLOR DOCKER_HOST DOCKER_CONTEXT DOCKER_CONFIG \
        DOCKER_CERT_PATH DOCKER_TLS_VERIFY BUILDKIT_PROGRESS; do
        [[ -n ${!name:-} ]] && keep+=("$name=${!name}")
    done
    env -i "${keep[@]}" docker compose --project-directory "${COMPOSE_ROOT:-$ROOT}" \
        --file "$(compose_file)" --env-file "${STACK_ENV_FILE:-$ROOT/.env}" \
        "${COMPOSE_PROFILE_ARGS[@]}" "$@"
}
compose_file() { echo "${STACK_COMPOSE_FILE:-${COMPOSE_ROOT:-$ROOT}/compose.yaml}"; }

# docker inspect of production's containers (a JSON array, empty when there are none).
production_containers() {
    local ids
    ids=$(docker ps --all --quiet --filter "label=com.docker.compose.project=$PRODUCTION_PROJECT") || return 1
    if [[ -z $ids ]]; then
        echo '[]'
    else
        # shellcheck disable=SC2086  # one argument per container id
        docker inspect $ids
    fi
}

# Dies unless the stack of ROOT, as docker compose resolves it with ENV_FILE (default ROOT/.env),
# shares nothing with production and keeps to its own DATA_DIR: project, images, settings, ports,
# host paths (scripts/lib/stack.py). Without interpolation, docker compose keeps env_file and
# label_file, which it otherwise merges into the settings.
assert_isolated_from_production() {  # assert_isolated_from_production [ENV_FILE]
    local env_file=${1:-$ROOT/.env} config raw containers
    [[ -f $env_file ]] || die "no $env_file: run scripts/dev-env.sh first"
    python3 "$SCRIPTS_LIB/stack.py" env "$env_file" > /dev/null || exit 1
    config=$(STACK_ENV_FILE=$env_file compose --profile '*' config --format json) \
        && raw=$(STACK_ENV_FILE=$env_file compose --profile '*' config --no-interpolate --format json) \
        || die "docker compose cannot resolve the stack of $env_file (see above)"
    containers=$(production_containers) || die "cannot list production's containers: is Docker running?"
    printf '{"config": %s, "raw": %s, "containers": %s}' "$config" "$raw" "$containers" \
        | python3 "$SCRIPTS_LIB/stack.py" check-isolation --env "$env_file" --project-dir "${COMPOSE_ROOT:-$ROOT}" \
            --compose-file "$(compose_file)" \
        || die "$env_file: this stack would share the above with production, or reach outside its DATA_DIR; nothing was done"
}

# Ignored files under android/ besides Gradle's own caches and outputs: they could end up in the
# release app (a stray keystore or APK in src/, a local.properties...).
android_stray_files() {  # android_stray_files ROOT
    git -C "$1" ls-files --others --ignored --exclude-standard --directory -- android \
        | grep -vE '^android/(\.gradle|\.kotlin|build|app/build)/' || true
}
