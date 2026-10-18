#!/usr/bin/env bash
# The gate: the checks of each area of the repository, as continuous integration runs them
# (.github/workflows/ci.yml calls this script, one area per job). It stops at the first area
# that fails, and never runs in production's checkout.
#
#   lint        the formatters and linters, without network, on read-only sources: Ruff (format and lint) and
#               mypy --strict for the Python, zizmor for the workflows, ShellCheck and shfmt for the shell scripts,
#               Biome for the web UI (ktlint, for the app, runs in the android area)
#   scripts     the unit tests of the scripts' modules (scripts/tests/), on the host's python3
#   web         the unit tests of the web UI (node --test, in a container without network)
#   server      the api's tests, in its test image, without network, read-only
#   ocr         the sandbox's unit tests, in its image, without network or models
#   android     the app's unit tests, lint and ktlint (scripts/build-apk.sh, never signed)
#   integration the integration tests of the scripts (scripts/integration_tests/): the scripts themselves, on the
#               host's python3, against throwaway repositories and a docker stand-in that builds and starts nothing
#
# --fix formats the code and applies the linters' safe fixes instead of checking. ktlint formats android/ in place.
# The other formatters work on a copy of the tracked files they format in server/, ocr/ and scripts/ (git add a new
# file first), and only their changes to those files come back (scripts/lib/formatting.py): read git diff before running
# what they changed. Every tool runs even after one that leaves findings, and the script then fails.
#
# Usage: scripts/check.sh [AREA...]
#        scripts/check.sh --fix
#   e.g. scripts/check.sh                 every area, in the order above
#        scripts/check.sh server web      those areas only
set -euo pipefail

readonly AREAS=(lint scripts web server ocr android integration)
readonly SHELLCHECK_DIGEST=sha256:61862eba1fcf09a484ebcc6feea46f1782532571a34ed51fedf90dd25f925a8d
readonly SHELLCHECK_IMAGE=koalaman/shellcheck:v0.11.0@$SHELLCHECK_DIGEST
readonly SHFMT_DIGEST=sha256:8c06884a35683d8763fba6c0d9484d11a61a96da65f8d497d6f625825a6043f2
readonly SHFMT_IMAGE=mvdan/shfmt:v3.14.1@$SHFMT_DIGEST
readonly FORMATTED_DIRECTORIES=(server ocr scripts)
# The files the formatters of the copy format, and nothing else: no other file comes back, such as a vendored file or a
# lock, whose change git diff would not let a reader judge.
readonly FORMATTED_PATHSPECS=('server/*.py' 'ocr/*.py' 'scripts/*.py' 'ocr/*.sh' 'scripts/*.sh'
    'server/scanmylib/web/*.js' 'server/scanmylib/web/*.json' 'server/scanmylib/web/*.css'
    ':(exclude)server/scanmylib/web/static/vendor/' ':(exclude)server/scanmylib/web/package-lock.json')
# Without .env (CI only), scripts/build-apk.sh reads its settings from the environment, which
# common.sh clears: they are handed back to it.
readonly CI_ANDROID_SETTINGS=("DATA_DIR=${DATA_DIR:-}" "ANDROID_DIR=${ANDROID_DIR:-}" "APP_VARIANT=${APP_VARIANT:-}")
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=lib/common.sh
source "$ROOT/scripts/lib/common.sh"
# git rebase --exec, which checks each commit of a branch, exports GIT_DIR from a worktree: a test's own git would
# then work on this repository instead of its throwaway one.
unset "${!GIT_@}"
readonly CHECKED_SOURCES=(-v "$ROOT:/src:ro")
IMAGE_ID_FILE=$(mktemp)
readonly IMAGE_ID_FILE
formatted_copy=

clean_up() {
    rm -f -- "$IMAGE_ID_FILE"
    # A formatter may have left directories without the write permission their removal needs.
    if [[ -n $formatted_copy ]]; then chmod -R u+rwX -- "$formatted_copy" && rm -rf -- "$formatted_copy"; fi
}
trap clean_up EXIT

usage() {
    sed -n '2,/^set /{/^set /d;s/^# \{0,1\}//;p}' "${BASH_SOURCE[0]}" >&2
    exit 2
}

# Each image is run by the id its build wrote, never by a tag: the gate of another worktree may
# build the same tag in between. The file is emptied first, and a failed build returns at once:
# set -e does not apply inside the command substitution that calls this, and an id left by an
# earlier build would run the wrong image.
build_image() {
    : > "$IMAGE_ID_FILE"
    docker build --iidfile "$IMAGE_ID_FILE" "$@" >&2 || return 1
    [[ -s $IMAGE_ID_FILE ]] || die "docker build wrote no image id to $IMAGE_ID_FILE"
    cat -- "$IMAGE_ID_FILE"
}

build_python_tools() {
    tar -C "$ROOT" -c scripts/lint/Dockerfile scripts/lint/requirements.lock server/requirements-test.lock \
        | build_image --file scripts/lint/Dockerfile -
}

build_web_tools() {
    tar -C "$ROOT" -c scripts/lint/Dockerfile.web server/scanmylib/web/package.json \
        server/scanmylib/web/package-lock.json \
        | build_image --file scripts/lint/Dockerfile.web -
}

run_tool() {
    docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true \
        --user "$(id -u):$(id -g)" "$@"
}

run_python_tool() {
    local image=$1 directory=$3
    local -n mounts=$2
    shift 3
    run_tool --tmpfs /tmp --env HOME=/tmp --env RUFF_CACHE_DIR=/tmp/ruff --env MYPY_CACHE_DIR=/tmp/mypy \
        "${mounts[@]}" -w "/src/$directory" "$image" "$@"
}

check_lint() {
    local python_tools web_tools shell_scripts
    python_tools=$(build_python_tools)
    run_python_tool "$python_tools" CHECKED_SOURCES . ruff format --check .
    run_python_tool "$python_tools" CHECKED_SOURCES . ruff check .
    run_python_tool "$python_tools" CHECKED_SOURCES server env MYPYPATH=tests mypy --config-file ../mypy.ini \
        scanmylib tests
    run_python_tool "$python_tools" CHECKED_SOURCES ocr env MYPYPATH=bench mypy --config-file ../mypy.ini \
        scanmylib_ocr tests bench
    run_python_tool "$python_tools" CHECKED_SOURCES scripts env MYPYPATH=lib:tests:integration_tests mypy \
        --config-file ../mypy.ini lib release.py e2e_test.py tests integration_tests
    run_python_tool "$python_tools" CHECKED_SOURCES . zizmor --offline --no-progress .github/workflows
    mapfile -d '' -t shell_scripts < <(python3 "$ROOT/scripts/lib/formatting.py" shell-scripts "$ROOT")
    wait "$!" || die "cannot list the shell scripts: see git's error above"
    run_tool "${CHECKED_SOURCES[@]}" -w /src "$SHELLCHECK_IMAGE" -- "${shell_scripts[@]}"
    run_tool "${CHECKED_SOURCES[@]}" -w /src "$SHFMT_IMAGE" -d -- "${shell_scripts[@]}"
    web_tools=$(build_web_tools)
    run_tool -v "$ROOT/server/scanmylib/web:/web:ro" "$web_tools" /tools/node_modules/.bin/biome ci --colors=off .
}

# ktlint writes android/ in place through scripts/build-apk.sh, which runs on the host: it runs before anything comes
# back from the copy that the other formatters write.
fix_everything() {
    local python_tools web_tools tree digests_file shell_scripts fixed_sources directory
    python_tools=$(build_python_tools)
    web_tools=$(build_web_tools)
    python3 "$ROOT/scripts/lib/formatting.py" check-hidden "$ROOT" "${FORMATTED_DIRECTORIES[@]}" android \
        || die "nothing was formatted: fix what the error above says, then run --fix again"
    run_android ktlintFormat || findings_remain=1
    formatted_copy=$(realpath -- "$(mktemp -d)")
    tree=$formatted_copy/tree
    digests_file=$formatted_copy/digests.json
    for directory in "${FORMATTED_DIRECTORIES[@]}" server/scanmylib/web; do
        mkdir -p -- "$tree/$directory"
    done
    mapfile -d '' -t shell_scripts < <(python3 "$ROOT/scripts/lib/formatting.py" make-copy "$ROOT" "$tree" \
        "$digests_file" "${FORMATTED_PATHSPECS[@]}")
    wait "$!" || die "only ktlint formatted (android/): fix what the error above says, then run --fix again"
    # Biome runs first on the copy, before any other formatter could turn a directory of it into a link.
    run_tool -v "$tree/server/scanmylib/web:/web" "$web_tools" /tools/node_modules/.bin/biome check --write \
        --colors=off . || findings_remain=1
    fixed_sources=("${CHECKED_SOURCES[@]}")
    for directory in "${FORMATTED_DIRECTORIES[@]}"; do
        fixed_sources+=(-v "$tree/$directory:/src/$directory")
    done
    run_python_tool "$python_tools" fixed_sources . ruff check --fix . || findings_remain=1
    run_python_tool "$python_tools" fixed_sources . ruff format . || findings_remain=1
    run_tool "${fixed_sources[@]}" -w /src "$SHFMT_IMAGE" -w -- "${shell_scripts[@]}" || findings_remain=1
    python3 "$ROOT/scripts/lib/formatting.py" bring-back "$ROOT" "$tree" "$digests_file" \
        || die "ktlint formatted android/ in place, and the error above says what came back from the copy: read git \
diff, fix the error, then run --fix again; first check the pinned image of a formatter that made a link or hid a change"
}

check_scripts() {
    python3 -m unittest discover -s "$ROOT/scripts/tests"
}

check_integration() {
    python3 -m unittest discover -s "$ROOT/scripts/integration_tests"
}

check_web() {
    run_tool -v "$ROOT/server/scanmylib/web:/web:ro" node:22-bookworm-slim node --test '/web/tests/*.test.js'
}

check_server() {
    local image
    image=$(build_image --target test "$ROOT/server")
    docker run --rm --network none --read-only --tmpfs /tmp "$image"
}

check_ocr() {
    local image
    image=$(build_image "$ROOT/ocr")
    run_tool --init --tmpfs /tmp -v "$ROOT/ocr:/app:ro" "$image" python3 -m unittest discover -s /app/tests
}

run_android() {
    local settings=() setting
    for setting in "${CI_ANDROID_SETTINGS[@]}"; do
        if [[ -n ${setting#*=} ]]; then settings+=("$setting"); fi
    done
    env "${settings[@]}" "$ROOT/scripts/build-apk.sh" "$@"
}

check_android() {
    run_android test lint ktlintCheck
}

check_area() {
    local area=$1
    case "$area" in
        lint) check_lint ;;
        scripts) check_scripts ;;
        web) check_web ;;
        server) check_server ;;
        ocr) check_ocr ;;
        android) check_android ;;
        integration) check_integration ;;
        *) die "no check for the area '$area'" ;;
    esac
}

is_area() {
    local name=$1 area
    for area in "${AREAS[@]}"; do
        if [[ $name == "$area" ]]; then return 0; fi
    done
    return 1
}

[[ ${1:-} == -h || ${1:-} == --help ]] && usage
fixing=0
if [[ ${1:-} == --fix ]]; then
    (($# == 1)) || die "--fix takes no area: it formats and fixes every one"
    fixing=1
    shift
fi
areas=("$@")
((${#areas[@]})) || areas=("${AREAS[@]}")
for area in "${areas[@]}"; do
    is_area "$area" || die "unknown area '$area': the areas are ${AREAS[*]}"
done

checkout=$(production_checkout) || die "cannot tell production's checkout (see above)"
if is_production_checkout "$ROOT" "$checkout"; then
    die "$ROOT is production's checkout, which holds production's release: check a worktree \
(see CLAUDE.md > Production)"
fi

if ((fixing)); then
    say "Formatting and fixing"
    findings_remain=0
    fix_everything
    ((findings_remain == 0)) || die "the findings above are left to fix by hand; read git diff before running what \
the tools changed"
    say "Formatted and fixed: read git diff, then run scripts/check.sh"
    exit 0
fi

for area in "${areas[@]}"; do
    say "Checking $area"
    check_area "$area"
done
say "Passed: ${areas[*]}"
