#!/usr/bin/env bash
# The gate: the checks of each area of the repository, as continuous integration runs them
# (.github/workflows/ci.yml calls this script, one area per job). It stops at the first area
# that fails, and never runs in production's checkout.
#
#   scripts     the tests of scripts/, on the host's python3 (standard library, a docker stand-in)
#   web         the unit tests of the web UI (node --test, in a container without network)
#   server      the api's tests, in its test image, without network, read-only
#   ocr         the sandbox's unit tests, in its image, without network or models
#   android     the app's unit tests and lint (scripts/build-apk.sh test lint, never signed)
#
# Usage: scripts/check.sh [AREA...]
#   e.g. scripts/check.sh                 every area, in the order above
#        scripts/check.sh server web      those areas only
set -euo pipefail

readonly AREAS=(scripts web server ocr android)
# Without .env (CI only), scripts/build-apk.sh reads its settings from the environment, which
# common.sh clears: they are handed back to it.
readonly CI_ANDROID_SETTINGS=("DATA_DIR=${DATA_DIR:-}" "ANDROID_DIR=${ANDROID_DIR:-}" "APP_VARIANT=${APP_VARIANT:-}")
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=lib/common.sh
source "$ROOT/scripts/lib/common.sh"
# git rebase --exec, which checks each commit of a branch, exports GIT_DIR from a worktree: a test's own git would
# then work on this repository instead of its throwaway one.
unset "${!GIT_@}"
IMAGE_ID_FILE=$(mktemp)
readonly IMAGE_ID_FILE
trap 'rm -f -- "$IMAGE_ID_FILE"' EXIT

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

check_scripts() {
    python3 -m unittest discover -s "$ROOT/scripts/tests"
}

check_web() {
    docker run --rm --network none --read-only --user "$(id -u):$(id -g)" \
        -v "$ROOT/server/scanmylib/web:/web:ro" \
        node:22-bookworm-slim node --test '/web/tests/*.test.js'
}

check_server() {
    local image
    image=$(build_image --target test "$ROOT/server")
    docker run --rm --network none --read-only --tmpfs /tmp "$image"
}

check_ocr() {
    local image
    image=$(build_image "$ROOT/ocr")
    docker run --rm --init --network none --read-only --tmpfs /tmp \
        --cap-drop ALL --security-opt no-new-privileges:true --user "$(id -u):$(id -g)" \
        -v "$ROOT/ocr:/app:ro" "$image" \
        python3 -m unittest discover -s /app/tests
}

check_android() {
    local settings=() setting
    for setting in "${CI_ANDROID_SETTINGS[@]}"; do
        if [[ -n ${setting#*=} ]]; then settings+=("$setting"); fi
    done
    env "${settings[@]}" "$ROOT/scripts/build-apk.sh" test lint
}

check_area() {
    local area=$1
    case "$area" in
        scripts) check_scripts ;;
        web) check_web ;;
        server) check_server ;;
        ocr) check_ocr ;;
        android) check_android ;;
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

for area in "${areas[@]}"; do
    say "Checking $area"
    check_area "$area"
done
say "Passed: ${areas[*]}"
