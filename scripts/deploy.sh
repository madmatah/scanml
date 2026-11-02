#!/usr/bin/env bash
# Deploys a published release to production: the only way production changes (see CLAUDE.md).
#
# Usage: scripts/deploy.sh [--dry-run] [--apk] [--first-install] [--allow-downgrade] [--new-sandbox]
#   --dry-run        check the preconditions and print every step without doing it
#   --apk            also build and publish the release APK (scripts/build-apk.sh)
#   --first-install  production has no database yet (DATA_DIR/state/scanmylib.db)
#   --allow-downgrade  deploy a release older than the one production runs, whose api must read
#                    the database as the newer release left it
#   --new-sandbox    install a new OCR sandbox next to the running one, SANDBOX_DIR.new (about an
#                    hour, 36 GiB free), switch to it at the restart, and keep the one it replaces
#                    as SANDBOX_DIR.replaced-<time>, for a rollback
#
# Preconditions, all checked before anything changes, under a lock (one deploy at a time from a
# checkout): run from production's checkout (the project directory of production's containers,
# else ~/Dev/scanmylib: scripts/lib/stack.py), clean (untracked files included, and no file marked
# assume-unchanged or skip-worktree, which git status would not compare), on a published release:
# HEAD is the commit of the tag vVERSION on origin (git ls-remote), which .github/workflows/release.yml
# created (git checkout vX.Y.Z); production's .env, in the strict format of scripts/lib/stack.py,
# with production's identity (COMPOSE_PROJECT_NAME=scanmylib, the OCR sandbox run by a user and a
# group other than root's, the release app), an existing DATA_DIR holding production's database
# (unless --first-install), an existing LIBRARY_DIR and an installed OCR sandbox (with
# --new-sandbox, a SANDBOX_DIR that holds a sandbox or nothing, that a rename moves whole, that
# neither is nor contains DATA_DIR and lies inside it only as DATA_DIR/sandbox, and that is,
# contains or lies inside none of LIBRARY_DIR, ANDROID_DIR, ANDROID_KEYSTORE_DIR and the checkout,
# no leftover SANDBOX_DIR.new, and 36 GiB free next to it:
# scripts/lib/stack.py); in a real run, the running api (/api/health) not on a newer release,
# unless --allow-downgrade. It never tags: releases are published on GitHub, and each installation
# deploys the ones it wants.
#
# The commit is exported first (git archive HEAD), and every docker compose call reads the
# compose.yaml of that export, so that nothing uncommitted, ignored or untracked is checked, built
# or started: the images are built from the export, and the containers are started with this
# checkout as project directory (production's containers record it: scripts/lib/stack.py).
#
# Steps:
#   1. images: api and ocr built from the export, on the current image of each base tag (--pull);
#      the running containers are not touched. The images production runs keep the tag
#      <prefix>-<service>:deployed (the images of its containers get it whenever it names another,
#      e.g. on the first run, or after a deploy that failed once the containers were recreated):
#      rebuilding moves :latest, and docker then forgets the previous image unless a tag still
#      names it
#   2. with --new-sandbox: ocr-setup installs a new sandbox into SANDBOX_DIR.new, while production
#      keeps running, through a temporary copy of .env that changes only SANDBOX_SETUP_DIR, its
#      output passed through cat -v (it is untrusted); in a rehearsal, that copy must keep the stack
#      isolated from production first. A failure leaves production unchanged and SANDBOX_DIR.new
#      with its setup.log
#   3. with the OCR sandbox (OCR_SERVICE=ocr): the new ocr image, named by its id (a failure puts
#      :latest back on the previous image), imports the engine's libraries from the sandbox it will
#      run (SANDBOX_DIR, or SANDBOX_DIR.new with --new-sandbox; python3 -m
#      scanmylib_ocr.engine_environment), in a container of its own with the isolation of the ocr
#      service (scripts/lib/engine_check.sh), its environment and its limits, the sandbox mounted
#      read-only, bounded in time, its output discarded: an image that cannot run the sandbox is
#      refused before production changes, and the failure prints the same command, to run by hand
#   4. backup of DATA_DIR/state (without its thumbnail cache) into
#      DATA_DIR/backups/state-<time>-v<version>/, the database copied with SQLite's online backup
#      (consistent while the api runs) and checked, right before the restart (what changes in the
#      seconds between the two is not in it); the 10 most recent backups are kept. If anything
#      fails before the restart, :latest goes back to :deployed: production is unchanged
#   5. restart: with --new-sandbox, ocr is stopped and the sandboxes are renamed (SANDBOX_DIR to
#      SANDBOX_DIR.replaced-<time>, SANDBOX_DIR.new to SANDBOX_DIR); then docker compose up -d api ocr,
#      waiting until both are healthy and the api reports VERSION
#   6. scripts/verify-sandbox.sh; if it fails, the OCR service is stopped
#   7. with the OCR sandbox (OCR_SERVICE=ocr): python3 -m scanmylib_ocr.engine_environment in the new
#      ocr container, which imports the engine's libraries with the GPU hidden and no model loaded,
#      bounded in time, its output discarded: only its exit status counts. If it fails, the OCR
#      service is stopped. Once it passes (once the isolation check passes, on the fake OCR, which
#      skips it), the new images become :deployed: production runs them
#   8. with --apk: scripts/build-apk.sh (the release build, signing, publication), then a check that
#      /api/health offers the published APK
# It runs no test suite: the code of a release was tested before it was published
# (.claude/rules/releases.md); its checks of the sandbox only import the engine's libraries.
# A real run ignores SIGHUP (a lost terminal does not stop it halfway) and is also logged to
# DATA_DIR/logs/deploy-<time>.log. On failure, it says what state production is in after the
# step that failed, and how to roll back (the :deployed images, the backup of the state, the moves
# of the sandboxes). The scripts never delete a sandbox: they only rename them.
#
# Rehearsal on a throwaway stack: SCANMYLIB_DEPLOY_REHEARSAL=<project> deploys the .env of this
# checkout instead, when its COMPOSE_PROJECT_NAME is <project> and the export passes the isolation
# check of scripts/dev.sh. The git checks are then only reported, and HEAD need not be a release
# (it is still what is checked, built and started: commit first), the fake OCR is allowed
# (OCR_SERVICE=ocr-fake, which skips the checks of the engine), and the app is the dev one.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=lib/common.sh
source "$ROOT/scripts/lib/common.sh"
# shellcheck source=lib/engine_check.sh
source "$ROOT/scripts/lib/engine_check.sh"

usage() {
    sed -n '/^# Usage:/,/^#   *as SANDBOX_DIR.replaced/{s/^# \{0,1\}//;p}' "${BASH_SOURCE[0]}" >&2
    exit 2
}

DRY_RUN=0 BUILD_APK=0 FIRST_INSTALL=0 ALLOW_DOWNGRADE=0 INSTALLS_NEW_SANDBOX=0
for arg in "$@"; do
    case $arg in
        --dry-run) DRY_RUN=1 ;;
        --apk) BUILD_APK=1 ;;
        --first-install) FIRST_INSTALL=1 ;;
        --allow-downgrade) ALLOW_DOWNGRADE=1 ;;
        --new-sandbox) INSTALLS_NEW_SANDBOX=1 ;;
        *) usage ;;
    esac
done
REHEARSAL=${SCANMYLIB_DEPLOY_REHEARSAL:-}
ENV_FILE=$ROOT/.env
readonly KEEP_BACKUPS=10
# The peak of an installation of the sandbox where no reflink shares its files (about 30 GiB before uv's cache
# is deleted), with the layers of the images and a margin.
readonly NEW_SANDBOX_BYTES=$((36 * 1024 * 1024 * 1024))
STAMP=$(date +%Y%m%d-%H%M%S)
cd "$ROOT"

# One deploy at a time from this checkout: the lock comes before any check.
if ! ((DRY_RUN)); then
    exec 9< "$ROOT"
    flock --nonblock 9 || die "another deploy is running from $ROOT"
fi

# --- Preconditions ------------------------------------------------------------------------------

problems=()
pass() { printf '  ok    %s\n' "$*"; }
info() { printf '  info  %s\n' "$*"; }
warn() { printf '  warn  %s\n' "$*"; }
fail() {
    printf '  FAIL  %s\n' "$*"
    problems+=("$*")
}
# A git precondition: enforced in production, only reported in a rehearsal.
git_fail() { if [[ -n $REHEARSAL ]]; then printf '  warn  %s (rehearsal: not enforced)\n' "$*"; else fail "$*"; fi; }

say "Preconditions${REHEARSAL:+ (rehearsal on $REHEARSAL)}"
head_commit=$(git rev-parse HEAD)
# The commit, whose compose.yaml every docker compose call below reads.
EXPORT=$(mktemp -d "${TMPDIR:-/tmp}/scanmylib-deploy.XXXXXX")
trap 'rm -rf -- "$EXPORT"' EXIT
chmod 755 "$EXPORT"
git archive --format=tar "$head_commit" | tar --extract --file - -C "$EXPORT"
# shellcheck disable=SC2034  # read by compose() of scripts/lib/common.sh
STACK_COMPOSE_FILE=$EXPORT/compose.yaml

# origin is only read for a production deploy that passes the local checks.
read_origin=1
[[ -z $REHEARSAL ]] || read_origin=0
if ! checkout=$(production_checkout); then
    fail "cannot tell production's checkout (see above)"
    read_origin=0
elif is_production_checkout "$ROOT" "$checkout"; then
    pass "production's checkout ($ROOT)"
else
    git_fail "not production's checkout: production runs from $checkout"
    read_origin=0
fi

changes=$(git status --porcelain --untracked-files=all)
if [[ -z $changes ]]; then
    pass "clean working tree, untracked files included"
else
    git_fail "uncommitted or untracked changes in $(wc -l <<< "$changes") file(s), e.g. $(head -n 1 <<< "$changes" | cut -c 4-)"
fi
hidden=$(hidden_changes "$ROOT")
if [[ -n $hidden ]]; then
    git_fail "files marked assume-unchanged or skip-worktree, whose changes git status hides: \
$(tr '\n' ' ' <<< "$hidden")(git update-index --no-assume-unchanged --no-skip-worktree FILE)"
fi

if [[ -n $REHEARSAL ]]; then
    printf '  skip  the release on origin (rehearsal: any commit)\n'
elif ! ((read_origin)); then
    printf '  skip  the release on origin (not production'"'"'s checkout)\n'
# Read on origin itself, in a dry run as in a real one: nothing local is trusted or updated.
elif release_error=$(release_problem "$ROOT"); then
    pass "the release v$(git show HEAD:VERSION | tr -d '[:space:]'), as published on origin (${head_commit:0:12})"
else
    fail "$release_error"
fi

declare -A STACK=()
service_options='' are_service_options_read=0
env_read=0
if [[ ! -f $ENV_FILE ]]; then
    fail "no $ENV_FILE (scripts/setup.sh writes production's)"
elif env_error=$(python3 "$SCRIPTS_LIB/stack.py" env "$ENV_FILE" 2>&1 > /dev/null); then
    load_env "$ENV_FILE" STACK
    env_read=1
    pass ".env in the strict format"
else
    fail "${env_error#error: }"
fi
PROJECT=${STACK[COMPOSE_PROJECT_NAME]:-}
IMAGE_PREFIX=${STACK[IMAGE_PREFIX]:-$PROJECT}
DATA_DIR=${STACK[DATA_DIR]:-}
LIBRARY_DIR=${STACK[LIBRARY_DIR]:-}
SANDBOX_DIR=${STACK[SANDBOX_DIR]:-}
API_PORT=${STACK[API_PORT]:-8765}
OCR_SERVICE=${STACK[OCR_SERVICE]:-ocr}

SANDBOX_PATH='' NEW_SANDBOX_DIR='' REPLACED_SANDBOX_DIR=''
check_new_sandbox() {
    local new_sandbox_places line paths_error containers android_dir=${STACK[ANDROID_DIR]:-$DATA_DIR/android}
    if ! new_sandbox_places=$(python3 "$SCRIPTS_LIB/stack.py" check-new-sandbox "$SANDBOX_DIR" --stamp "$STAMP" \
        --needed-bytes "$NEW_SANDBOX_BYTES" --data-dir "$DATA_DIR" --other-path "LIBRARY_DIR=$LIBRARY_DIR" \
        --other-path "ANDROID_DIR=$android_dir" \
        --other-path "ANDROID_KEYSTORE_DIR=${STACK[ANDROID_KEYSTORE_DIR]:-$android_dir/keystore}" \
        --other-path "the checkout=$ROOT" 2>&1); then
        while IFS= read -r line; do
            fail "--new-sandbox: ${line#  - }"
        done <<< "$new_sandbox_places"
        return
    fi
    NEW_SANDBOX_DIR=$(sed -n 's/^NEW=//p' <<< "$new_sandbox_places")
    REPLACED_SANDBOX_DIR=$(sed -n 's/^REPLACED=//p' <<< "$new_sandbox_places")
    SANDBOX_PATH=${NEW_SANDBOX_DIR%.new}
    pass "a new sandbox goes to $NEW_SANDBOX_DIR, and the one it replaces to $REPLACED_SANDBOX_DIR"
    # A rehearsal renames only its own sandboxes, never production's.
    [[ -n $REHEARSAL ]] || return 0
    if ! containers=$(production_containers); then
        fail "cannot list production's containers: is Docker running?"
    elif paths_error=$(python3 "$SCRIPTS_LIB/stack.py" check-paths "SANDBOX_DIR=$SANDBOX_PATH" \
        "the new sandbox=$NEW_SANDBOX_DIR" "the replaced sandbox=$REPLACED_SANDBOX_DIR" 2>&1 <<< "$containers"); then
        pass "the rehearsal's sandboxes are not production's"
    else
        while IFS= read -r line; do
            fail "${line#  - }"
        done <<< "$paths_error"
    fi
}

# The stack's identity and paths, once .env could be read.
if ((env_read)); then
    if [[ -z $REHEARSAL ]]; then
        if [[ $PROJECT == "$PRODUCTION_PROJECT" ]]; then
            pass ".env is production's (COMPOSE_PROJECT_NAME=$PROJECT)"
        else
            fail ".env is not production's: COMPOSE_PROJECT_NAME is '${PROJECT:-unset}', not $PRODUCTION_PROJECT"
        fi
        [[ $IMAGE_PREFIX == "$PRODUCTION_PROJECT" ]] || fail "IMAGE_PREFIX is '$IMAGE_PREFIX', not $PRODUCTION_PROJECT"
        [[ $OCR_SERVICE == ocr ]] || fail "OCR_SERVICE is '$OCR_SERVICE': production runs the OCR sandbox (ocr)"
        [[ ${STACK[APP_VARIANT]:-release} == release ]] \
            || fail "APP_VARIANT is '${STACK[APP_VARIANT]}': production publishes the release app"
    elif [[ $REHEARSAL == "$PRODUCTION_PROJECT" ]]; then
        fail "SCANMYLIB_DEPLOY_REHEARSAL cannot be the production project"
    elif [[ $PROJECT != "$REHEARSAL" ]]; then
        fail "COMPOSE_PROJECT_NAME in .env is '${PROJECT:-unset}', not the rehearsal project $REHEARSAL"
    # Checked twice: as the build resolves it (the export as project directory) and as up, ps and
    # stop resolve it (this checkout as project directory: relative extends files and bind sources
    # are read from this checkout, uncommitted changes included).
    elif isolation=$( (COMPOSE_ROOT=$EXPORT assert_isolated_from_production "$ENV_FILE") 2>&1 \
        && (assert_isolated_from_production "$ENV_FILE") 2>&1); then
        pass "the rehearsal stack $PROJECT shares nothing with production"
    else
        fail "the rehearsal stack is not isolated from production:"
        # shellcheck disable=SC2001  # indents every line of a multi-line message
        sed 's/^/        /' <<< "$isolation"
    fi
    [[ $OCR_SERVICE == ocr || $OCR_SERVICE == ocr-fake ]] || fail "OCR_SERVICE must be ocr or ocr-fake, not '$OCR_SERVICE'"

    if [[ $DATA_DIR != /* ]]; then
        fail "DATA_DIR in .env must be an absolute path, not '$DATA_DIR'"
    elif [[ -f $DATA_DIR/state/scanmylib.db ]]; then
        pass "DATA_DIR $DATA_DIR holds the database (state/scanmylib.db)"
    elif ((FIRST_INSTALL)); then
        pass "DATA_DIR $DATA_DIR (first installation: no database yet)"
    elif [[ ! -d $DATA_DIR ]]; then
        fail "DATA_DIR $DATA_DIR is not a directory"
    else
        fail "no database in $DATA_DIR/state: is DATA_DIR right? (--first-install for a first installation)"
    fi
    if [[ $LIBRARY_DIR != /* ]]; then
        fail "LIBRARY_DIR in .env must be an absolute path, not '$LIBRARY_DIR'"
    elif [[ -d $LIBRARY_DIR ]]; then
        pass "LIBRARY_DIR $LIBRARY_DIR"
    elif ((FIRST_INSTALL)) && [[ ! -e $LIBRARY_DIR ]]; then
        pass "LIBRARY_DIR $LIBRARY_DIR (first installation: created at the restart)"
    else
        fail "LIBRARY_DIR $LIBRARY_DIR is not a directory"
    fi
    if ((INSTALLS_NEW_SANDBOX)) && [[ $OCR_SERVICE != ocr ]]; then
        fail "--new-sandbox installs the OCR sandbox, which OCR_SERVICE=$OCR_SERVICE does not run"
    fi
    if [[ $OCR_SERVICE == ocr ]]; then
        # docker run --mount reads a comma as the start of another of its settings.
        if [[ $SANDBOX_DIR != /* || $SANDBOX_DIR == *,* ]]; then
            fail "SANDBOX_DIR in .env must be an absolute path without a comma, not '$SANDBOX_DIR'"
        elif ((INSTALLS_NEW_SANDBOX)); then
            check_new_sandbox
        elif [[ -f $SANDBOX_DIR/MANIFEST.json ]]; then
            pass "OCR sandbox installed in $SANDBOX_DIR"
        else
            fail "no OCR sandbox in SANDBOX_DIR ('$SANDBOX_DIR'): scripts/setup.sh installs the first one, and \
--new-sandbox one into an existing SANDBOX_DIR that holds nothing"
        fi
        # The check before the restart runs engine code ahead of any isolation check, as this user and group.
        for id_setting in SCANMYLIB_UID SCANMYLIB_GID; do
            [[ ${STACK[$id_setting]:-1000} =~ ^[1-9][0-9]*$ ]] || fail "$id_setting in .env must be a number other \
than root's 0, not '${STACK[$id_setting]}'"
        done
    fi
fi

VERSION=$(tr -d '[:space:]' 2> /dev/null < VERSION || true)
if [[ $VERSION =~ ^[0-9]{1,3}\.[0-9]{1,2}\.[0-9]{1,2}$ ]]; then
    pass "VERSION $VERSION"
else
    fail "VERSION must be MAJOR.MINOR.PATCH (minor and patch below 100), not '$VERSION'"
fi

# An older release than production runs may not read the database the newer one migrated, and its
# app has a lower versionCode, which phones refuse. A dry run sends no request to the api.
if ((env_read)) && [[ -z $REHEARSAL && $VERSION =~ ^[0-9]{1,3}\.[0-9]{1,2}\.[0-9]{1,2}$ ]] && ! ((FIRST_INSTALL)); then
    if ((DRY_RUN)); then
        info "a real run checks that production does not run a release newer than $VERSION (/api/health)"
    else
        running=$(curl -fsS --max-time 3 "http://127.0.0.1:$API_PORT/api/health" 2> /dev/null \
            | python3 -c 'import json, sys; print(json.load(sys.stdin).get("version", ""))' 2> /dev/null || true)
        if [[ -z $running ]]; then
            warn "cannot read the version of the running api (http://127.0.0.1:$API_PORT/api/health): not compared"
        elif [[ ! $running =~ ^[0-9]{1,3}\.[0-9]{1,2}\.[0-9]{1,2}$ ]]; then
            warn "the running api reports '$running', not a release: not compared"
        elif [[ $running != "$VERSION" && $(printf '%s\n' "$VERSION" "$running" | sort -V | tail -n 1) == "$running" ]]; then
            if ((ALLOW_DOWNGRADE)); then
                warn "production runs $running, newer than $VERSION: a downgrade (--allow-downgrade)"
            else
                fail "production runs $running, newer than this release $VERSION: check out $running or a later \
release (--allow-downgrade to go back, if $VERSION reads the database as $running left it)"
            fi
        else
            pass "production runs ${running}: not a newer release"
        fi
    fi
fi

if ((BUILD_APK)); then
    stray=$(android_stray_files "$ROOT")
    if [[ -z $stray ]]; then
        pass "no stray ignored file under android/ (--apk)"
    else
        fail "ignored files under android/ could end up in the release app: $(tr '\n' ' ' <<< "$stray")"
    fi
fi

if ! docker info --format '{{.ServerVersion}}' > /dev/null 2>&1; then
    fail "cannot reach Docker"
elif ((env_read)); then
    if config_error=$(compose config --quiet 2>&1); then
        pass "docker compose resolves the stack"
        # What the restart changes besides the images: compose.yaml or .env.
        while read -r service hash; do
            [[ -n $service ]] || continue
            running=$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" \
                --filter "label=com.docker.compose.service=$service" | head -n 1)
            current=
            [[ -n $running ]] && current=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.config-hash"}}' "$running")
            if [[ -z $current ]]; then
                info "$service is not running yet"
            elif [[ $current == "$hash" ]]; then
                info "$service: same configuration as the running container (config hash ${hash:0:12})"
            else
                info "$service: the restart applies a new configuration (config hash ${current:0:12} -> ${hash:0:12})"
            fi
        done < <(compose config --hash "api,$OCR_SERVICE" 2> /dev/null || true)
        # Read here rather than at the check, which comes after the build and an installation.
        if [[ $OCR_SERVICE == ocr ]]; then
            if service_options=$(compose config --format json | python3 "$SCRIPTS_LIB/stack.py" sandbox-check-options \
                2>&1); then
                are_service_options_read=1
                pass "the check of the sandbox takes the environment and the limits of the ocr service"
            else
                fail "the check of the sandbox cannot take the settings of the ocr service: ${service_options#error: }"
            fi
        fi
    else
        fail "docker compose cannot resolve the stack: $(tail -n 1 <<< "$config_error")"
    fi
fi

if ((${#problems[@]})) && ! ((DRY_RUN)); then
    printf '\nRefusing to deploy:\n' >&2
    printf '  - %s\n' "${problems[@]}" >&2
    if [[ -z $PROJECT ]]; then
        printf '\nProduction'"'"'s .env is written by scripts/setup.sh (COMPOSE_PROJECT_NAME=scanmylib...).\n' >&2
    fi
    exit 1
fi

# --- Steps --------------------------------------------------------------------------------------

STEP=preconditions BACKUP='' previous_version='' tee_pid='' ENV_COPY=''
# The renames of the sandboxes that the restart made, which a rollback undoes.
is_replaced_sandbox_moved=0 is_new_sandbox_moved=0
# The check of the sandbox before the restart, which a failure prints to run by hand.
SANDBOX_CHECK=()
# The images that can be put back: those production runs, tagged :deployed.
deployed_images=()
# How the failure messages name the stack and docker compose: production through scripts/prod.sh
# (its .env only, in its checkout), a rehearsal through scripts/dev.sh.
WHO=Production COMPOSE_HINT="scripts/prod.sh compose"
[[ -n $REHEARSAL ]] && WHO="The rehearsal stack $PROJECT" COMPOSE_HINT="scripts/dev.sh compose"
if ! ((DRY_RUN)); then
    # From here on, losing the terminal (SIGHUP) does not stop the deploy halfway; the log is
    # written even if the terminal is gone (tee ignores errors on its outputs).
    trap '' HUP
    mkdir -p "$DATA_DIR/logs"
    LOG=$DATA_DIR/logs/deploy-$STAMP.log
    exec > >(tee --output-error=warn -a "$LOG") 2>&1
    tee_pid=$!
    echo "Deploying $PROJECT $VERSION (${head_commit:0:12}) at $STAMP; log: $LOG"
fi

print_command() {
    local shown=("$@") hint
    if [[ $1 == compose ]]; then
        read -ra hint <<< "$COMPOSE_HINT"
        shown=("${hint[@]}" "${@:2}")
    fi
    printf '  %s' "$( ((DRY_RUN)) && echo 'would run:' || echo '$')"
    printf ' %q' "${shown[@]}"
    printf '\n'
}

# Runs a command, or only prints it in a dry run.
run() {
    print_command "$@"
    ((DRY_RUN)) || "$@"
}

stop_ocr_and_die() {
    local reason=$1 failure=$2
    stop_ocr_service "$COMPOSE_HINT" "$OCR_SERVICE" "$reason"
    die "$failure"
}

# Puts :latest back on the images of the last successful deploy.
restore_deployed_images() {
    local image
    for image in "${deployed_images[@]}"; do
        docker tag "$image:deployed" "$image:latest" \
            && echo "  $image:latest is $image:deployed again" \
            || echo "  could not restore $image: docker tag $image:deployed $image:latest"
    done
}

rollback_help() {
    local entry
    echo "To roll back to the previous version (${previous_version:-unknown}), in $ROOT:"
    echo "  $COMPOSE_HINT stop api $OCR_SERVICE"
    for entry in "${deployed_images[@]}"; do
        echo "  docker tag $entry:deployed $entry:latest"
    done
    if ((is_new_sandbox_moved)); then
        echo "  mv -T $SANDBOX_PATH $SANDBOX_PATH.failed-$STAMP"
    fi
    if ((is_replaced_sandbox_moved)); then
        echo "  mv -T $REPLACED_SANDBOX_DIR $SANDBOX_PATH"
    fi
    if [[ -n $BACKUP ]]; then
        echo "  # the state as this deploy left it is kept aside; the backup is the state right before the"
        echo "  # restart (the new api may have upgraded the database schema, which older versions refuse):"
        echo "  mv $DATA_DIR/state $DATA_DIR/state.failed-$STAMP"
        echo "  cp -a $BACKUP $DATA_DIR/state"
    fi
    echo "  $COMPOSE_HINT up -d --no-build api $OCR_SERVICE"
    echo "Pages uploaded since the restart stay in the library but not in the restored database."
    echo "Then fix the problem in a new release before deploying again."
}

print_replaced_sandbox() {
    if ((is_replaced_sandbox_moved)); then
        echo "The replaced sandbox is kept for a rollback in $REPLACED_SANDBOX_DIR. To go back to it, in $ROOT:"
        echo "  $COMPOSE_HINT stop $OCR_SERVICE"
        echo "  mv -T $SANDBOX_PATH $SANDBOX_PATH.rolled-back-$STAMP"
        echo "  mv -T $REPLACED_SANDBOX_DIR $SANDBOX_PATH"
        echo "Then check out the tag of the previous release with git checkout, and deploy it again:"
        if [[ -n $REHEARSAL ]]; then
            printf '  SCANMYLIB_DEPLOY_REHEARSAL=%q scripts/deploy.sh --allow-downgrade\n' "$REHEARSAL"
        else
            echo "  scripts/deploy.sh --allow-downgrade"
        fi
        echo "Once going back is no longer wanted:"
        echo "  rm -rf $REPLACED_SANDBOX_DIR"
    fi
}

# setup.log is written by untrusted code: reading a link would show a file of the host.
print_new_sandbox_left() {
    local log=$NEW_SANDBOX_DIR/setup.log
    echo "The new sandbox is left in $NEW_SANDBOX_DIR."
    if [[ -f $log && ! -L $log ]]; then
        echo "Read its log through cat -v: cat -v $log"
    else
        echo "Its setup.log is missing or not a regular file: do not read it."
    fi
    echo "Then remove it before deploying again: rm -rf $NEW_SANDBOX_DIR"
}

on_exit() {
    local status=$?
    if [[ -n $EXPORT ]]; then rm -rf -- "$EXPORT"; fi
    if [[ -n $ENV_COPY ]]; then rm -f -- "$ENV_COPY"; fi
    if ((status)) && [[ $STEP != 'done' ]]; then
        printf '\nDEPLOY FAILED during the step "%s" (exit %s).\n' "$STEP" "$status"
        case $STEP in
            preconditions) ;;
            images | sandbox | check | backup)
                restore_deployed_images
                echo "$WHO is unchanged: the previous containers still run, and the image tags point to the"
                echo "previous images again. Fix the problem, then deploy again."
                if [[ $STEP == check ]] && ((${#SANDBOX_CHECK[@]})); then
                    echo "The new image could not import the engine's libraries from ${NEW_SANDBOX_DIR:-$SANDBOX_DIR}."
                    echo "To see why:"
                    print_sandbox_check_diagnostic "${SANDBOX_CHECK[@]}"
                    if ! ((INSTALLS_NEW_SANDBOX)); then
                        echo "If the new image needs a new sandbox, deploy with --new-sandbox, which installs one next"
                        echo "to the running one (README.md > Updating)."
                    fi
                fi
                if [[ $STEP != images ]] && ((INSTALLS_NEW_SANDBOX)) && [[ -e $NEW_SANDBOX_DIR ]]; then
                    print_new_sandbox_left
                fi
                ;;
            restart)
                echo "$WHO may be down or running the new version $VERSION: the restart did not complete, or"
                echo "the new api is unhealthy or does not report $VERSION ($COMPOSE_HINT ps; $COMPOSE_HINT logs api)."
                rollback_help
                ;;
            isolation)
                echo "$WHO runs $VERSION, but its OCR service failed the isolation check (above) and was stopped:"
                echo "pages wait in the queue. Fix the isolation and deploy again, or roll back."
                rollback_help
                ;;
            engine)
                echo "$WHO runs $VERSION, but the engine of its OCR service failed the check of its environment in"
                echo "the new image, and the OCR service was stopped: pages wait in the queue. To see why, in $ROOT:"
                print_engine_check_steps "$COMPOSE_HINT" "$OCR_SERVICE"
                echo "Then fix the image or the sandbox and deploy again, or roll back."
                rollback_help
                ;;
            apk)
                echo "$WHO runs $VERSION (healthy, sandbox isolated, its images tagged :deployed); the APK was"
                echo "not published, or the api does not offer it to the phones (its metadata, scanmylib.json):"
                echo "the phones keep the previous app. Fix the problem, then run scripts/build-apk.sh here"
                echo "(or roll back)."
                [[ -n $BACKUP ]] && echo "Backup of the state before the restart: $BACKUP"
                print_replaced_sandbox
                ;;
        esac
    fi
    if [[ -n $tee_pid ]]; then
        exec >&- 2>&-
        wait "$tee_pid" 2> /dev/null || true
    fi
}
trap on_exit EXIT

STEP=images
say "1. Images"
for service in api ocr; do
    image=$IMAGE_PREFIX-$service
    deployed=$(docker image inspect --format '{{.Id}}' "$image:deployed" 2> /dev/null || true)
    # What the service's container runs is what a rollback puts back: :deployed names it.
    container=$(docker ps --all --quiet --filter "label=com.docker.compose.project=$PROJECT" \
        --filter "label=com.docker.compose.service=$service" --filter "label=com.docker.compose.oneoff=False" \
        | head -n 1)
    running=
    [[ -n $container ]] && running=$(docker inspect --format '{{.Image}}' "$container")
    if [[ -n $running && $running != "$deployed" ]]; then
        if [[ -n $deployed ]]; then
            warn "$image:deployed ($deployed) is not the image $service runs ($running), e.g. after a deploy that \
failed once the containers were recreated: it names the running image again"
        else
            latest=$(docker image inspect --format '{{.Id}}' "$image:latest" 2> /dev/null || true)
            [[ $latest == "$running" ]] || info "$image:latest (${latest:-none}) is not the image $service runs"
        fi
        run docker tag "$running" "$image:deployed"
        deployed=$running
    fi
    if [[ -n $deployed ]]; then
        deployed_images+=("$image")
        info "$image:deployed is $deployed"
    fi
done
echo "  the commit ${head_commit:0:12}, exported to $EXPORT"
COMPOSE_ROOT=$EXPORT run compose build --pull api ocr
# A failure puts :latest back on the previous image before it prints the check to run by hand: both name the new one.
NEW_OCR_IMAGE=$IMAGE_PREFIX-ocr:latest
if [[ $OCR_SERVICE == ocr ]] && ! ((DRY_RUN)); then
    NEW_OCR_IMAGE=$(docker image inspect --format '{{.Id}}' "$IMAGE_PREFIX-ocr:latest") \
        || die "cannot read the id of the new image $IMAGE_PREFIX-ocr:latest (above)"
    [[ -n $NEW_OCR_IMAGE ]] || die "docker gave no id for the new image $IMAGE_PREFIX-ocr:latest"
fi

STEP=sandbox
say "2. New sandbox"
if ! ((INSTALLS_NEW_SANDBOX)); then
    echo "  skipped (no --new-sandbox)"
elif [[ -z $NEW_SANDBOX_DIR ]]; then
    echo "  skipped: no place for a new sandbox (see the preconditions)"
else
    echo "  production keeps running meanwhile; until this deployment ends, :latest names the new images, so do"
    echo "  not run $COMPOSE_HINT up"
    # The copy changes nothing else: docker compose reads the stack as from .env, but for where ocr-setup installs.
    ENV_COPY=$(mktemp "${TMPDIR:-/tmp}/scanmylib-env.XXXXXX")
    python3 "$SCRIPTS_LIB/stack.py" env "$ENV_FILE" --set "SANDBOX_SETUP_DIR=$NEW_SANDBOX_DIR" > "$ENV_COPY"
    # As .env was checked before the build, and before ocr-setup writes anywhere.
    if [[ -z $REHEARSAL ]]; then
        :
    elif (COMPOSE_ROOT=$EXPORT assert_isolated_from_production "$ENV_COPY") \
        && (assert_isolated_from_production "$ENV_COPY"); then
        echo "  the copy of .env that installs the new sandbox shares nothing with production"
    else
        ((DRY_RUN)) || die "the copy of .env that installs the new sandbox is not isolated from production (above)"
        problems+=("the copy of .env that installs the new sandbox is not isolated from production (above)")
    fi
    run mkdir "$NEW_SANDBOX_DIR"
    printf '  %s docker compose, with .env but SANDBOX_SETUP_DIR=%s: ' \
        "$( ((DRY_RUN)) && echo 'would run' || echo '$')" "$NEW_SANDBOX_DIR"
    echo "--profile setup run --rm -T --pull never ocr-setup < /dev/null 2>&1 | cat -v"
    if ! ((DRY_RUN)); then
        # Untrusted output: no terminal (-T, no stdin), and every control character escaped.
        STACK_ENV_FILE=$ENV_COPY compose --profile setup run --rm -T --pull never ocr-setup < /dev/null 2>&1 | cat -v \
            || die "the installation of the new sandbox failed (above)"
        [[ -f $NEW_SANDBOX_DIR/MANIFEST.json ]] || die "the installation left no $NEW_SANDBOX_DIR/MANIFEST.json"
        echo "  installed in $NEW_SANDBOX_DIR"
    fi
fi

# Before the backup and the restart, so that production still runs when the new image cannot run the sandbox.
STEP=check
say "3. The new image against the sandbox"
checked_sandbox=$SANDBOX_DIR
if ((INSTALLS_NEW_SANDBOX)); then
    checked_sandbox=$NEW_SANDBOX_DIR
fi
if [[ $OCR_SERVICE != ocr ]]; then
    echo "  skipped (the fake OCR runs no engine)"
elif ! ((are_service_options_read)); then
    echo "  skipped: the settings of the ocr service could not be read (see the preconditions)"
else
    sandbox_check_options=()
    [[ -z $service_options ]] || mapfile -t sandbox_check_options <<< "$service_options"
    sandbox_check_name=$IMAGE_PREFIX-sandbox-check-$STAMP
    build_sandbox_check SANDBOX_CHECK "$sandbox_check_name" "$NEW_OCR_IMAGE" "$checked_sandbox" \
        "${STACK[SCANMYLIB_UID]:-1000}:${STACK[SCANMYLIB_GID]:-1000}" "${sandbox_check_options[@]}"
    if ((DRY_RUN)); then
        print_command timeout --kill-after=10 "$ENGINE_CHECK_BOUND_SECONDS" "${SANDBOX_CHECK[@]}"
    else
        sandbox_check_status=0
        run_sandbox_check "$sandbox_check_name" "${SANDBOX_CHECK[@]}" || sandbox_check_status=$?
        ((sandbox_check_status == 0)) \
            || die "the new image failed the check of the sandbox (exit $sandbox_check_status)"
        echo "  the new image imports the engine's libraries from $checked_sandbox"
    fi
fi

STEP=backup
say "4. Backup of the state"
BACKUP_NAME=state-$(date +%Y%m%d-%H%M%S.%N)-v$VERSION
backup_state() {
    local state=$DATA_DIR/state backups=$DATA_DIR/backups
    if [[ ! -d $state ]]; then
        echo "  no $state yet: nothing to back up"
        return
    fi
    mkdir -p "$backups"
    # Left by an interrupted backup: never complete.
    find "$backups" -mindepth 1 -maxdepth 1 -type d -name '*.partial' -exec rm -rf -- {} +
    BACKUP=$backups/$BACKUP_NAME
    python3 - "$state" "$BACKUP" << 'PY'
"""Copies a state directory, except the thumbnail cache (rebuilt by the api): the SQLite database
through the online backup API, which gives a consistent copy while the api writes to it, every
other file as is. Nothing is left behind on failure."""

import os
import shutil
import sqlite3
import sys
from pathlib import Path

state, backup = sys.argv[1:]
partial = backup + ".partial"
os.makedirs(partial, mode=0o700)
try:
    database = os.path.join(state, "scanmylib.db")
    skipped = {"scanmylib.db", "scanmylib.db-wal", "scanmylib.db-shm", "scanmylib.db-journal", "thumbs"}
    for entry in os.scandir(state):
        if entry.name in skipped:
            continue
        target = os.path.join(partial, entry.name)
        if entry.is_dir(follow_symlinks=False):
            shutil.copytree(entry.path, target, symlinks=True)
        else:
            shutil.copy2(entry.path, target, follow_symlinks=False)
    if os.path.exists(database):
        try:
            source = sqlite3.connect(Path(database).as_uri() + "?mode=ro", uri=True)
            source.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except sqlite3.OperationalError:
            source = sqlite3.connect(database)  # read-only needs the -shm file of a running api
        copy = sqlite3.connect(os.path.join(partial, "scanmylib.db"))
        source.backup(copy)
        source.close()
        result = copy.execute("PRAGMA integrity_check").fetchone()[0]
        copy.close()
        if result != "ok":
            sys.exit(f"integrity check of the copied database: {result}")
    os.rename(partial, backup)
except BaseException:
    shutil.rmtree(partial, ignore_errors=True)
    raise
PY
    echo "  $BACKUP ($(du -sh "$BACKUP" | cut -f 1))"
    local old
    find "$backups" -mindepth 1 -maxdepth 1 -type d -name 'state-*' ! -name '*.partial' -printf '%f\n' \
        | sort | head -n "-$KEEP_BACKUPS" | while read -r old; do
        rm -rf -- "${backups:?}/$old"
        echo "  removed the old backup $old (the $KEEP_BACKUPS most recent are kept)"
    done
}
if ((DRY_RUN)); then
    echo "  would copy $DATA_DIR/state (without thumbs/) to $DATA_DIR/backups/$BACKUP_NAME (SQLite online"
    echo "  backup of scanmylib.db, integrity check), and keep the $KEEP_BACKUPS most recent backups"
else
    backup_state
fi
# The restart starts :latest: it must still be the image that the check passed.
if [[ $OCR_SERVICE == ocr ]] && ! ((DRY_RUN)); then
    latest_ocr_image=$(docker image inspect --format '{{.Id}}' "$IMAGE_PREFIX-ocr:latest" 2> /dev/null || true)
    [[ $latest_ocr_image == "$NEW_OCR_IMAGE" ]] || die "$IMAGE_PREFIX-ocr:latest is now ${latest_ocr_image:-no image}, \
not the image checked against the sandbox ($NEW_OCR_IMAGE): deploy again"
fi

STEP=restart
say "5. Restart"
if ((DRY_RUN)); then
    echo "  would read the version of the running api (http://127.0.0.1:$API_PORT/api/health)"
else
    previous_version=$(curl -fsS --max-time 3 "http://127.0.0.1:$API_PORT/api/health" 2> /dev/null \
        | python3 -c 'import json, sys; print(json.load(sys.stdin).get("version", ""))' 2> /dev/null || true)
    [[ -n $previous_version ]] && info "the running api reports version $previous_version"
fi
# Created here, before Docker would create missing bind-mount sources as root.
run mkdir -p "$DATA_DIR/state" "$DATA_DIR/run" "$DATA_DIR/ocr-cache" "$DATA_DIR/app" "$LIBRARY_DIR"
if ((INSTALLS_NEW_SANDBOX)); then
    run compose stop ocr
    run mv -T "$SANDBOX_PATH" "$REPLACED_SANDBOX_DIR"
    ((DRY_RUN)) || is_replaced_sandbox_moved=1
    run mv -T "$NEW_SANDBOX_DIR" "$SANDBOX_PATH"
    ((DRY_RUN)) || is_new_sandbox_moved=1
fi
other=$([[ $OCR_SERVICE == ocr ]] && echo ocr-fake || echo ocr)
if [[ -n $(compose ps -aq "$other" 2> /dev/null) ]]; then
    # Both OCR services serve the same socket: never run them together.
    run compose rm --stop --force "$other"
fi
run compose up -d --no-build --wait --wait-timeout 300 api "$OCR_SERVICE"
if ((DRY_RUN)); then
    echo "  would check that http://127.0.0.1:$API_PORT/api/health reports version $VERSION"
else
    reported=$(curl -fsS --max-time 5 "http://127.0.0.1:$API_PORT/api/health" \
        | python3 -c 'import json, sys; print(json.load(sys.stdin).get("version"))') \
        || die "the api does not answer on http://127.0.0.1:$API_PORT/api/health"
    [[ $reported == "$VERSION" ]] || die "the api reports version '$reported', not $VERSION"
    echo "  api healthy, version $reported"
fi

STEP=isolation
say "6. Sandbox isolation"
ocr_container=
if ((DRY_RUN)); then
    echo "  would run: scripts/verify-sandbox.sh on the $OCR_SERVICE container (and stop it if it fails)"
else
    ocr_container=$(compose ps -q "$OCR_SERVICE" 2> /dev/null || true)
    scripts/verify-sandbox.sh "$ocr_container" \
        || stop_ocr_and_die "which failed the isolation check" "scripts/verify-sandbox.sh failed"
fi

# After the isolation check, so that no engine code runs in a sandbox that failed it.
STEP=engine
say "7. Engine's environment"
if [[ $OCR_SERVICE != ocr ]]; then
    echo "  skipped (the fake OCR runs no engine)"
elif ((DRY_RUN)); then
    echo "  would run: timeout --kill-after=10 $ENGINE_CHECK_BOUND_SECONDS docker exec <the ocr container> python3 -m \
scanmylib_ocr.engine_environment, its output discarded (and stop it if it fails)"
else
    engine_check_status=0
    check_engine_environment "$ocr_container" || engine_check_status=$?
    # timeout ends only the docker CLI: stopping the service ends the check inside it.
    if ((engine_check_status)); then
        stop_ocr_and_die "whose engine's environment failed its check (exit $engine_check_status)" \
            "the check of the engine's environment failed (python3 -m scanmylib_ocr.engine_environment)"
    fi
fi
# Production runs the new images: those of its containers, which :latest may no longer name, are now the ones to put
# back. With the fake OCR, no container runs the ocr image, and :latest names the one built.
for service in api ocr; do
    image=$IMAGE_PREFIX-$service
    running_image=$image:latest
    if [[ $service == api || $OCR_SERVICE == ocr ]]; then
        if ((DRY_RUN)); then
            echo "  would tag $image:deployed on the image that $service runs"
            continue
        fi
        container=$(compose ps -q "$service" 2> /dev/null | head -n 1 || true)
        running_image=
        [[ -z $container ]] || running_image=$(docker inspect --format '{{.Image}}' "$container" 2> /dev/null || true)
        if [[ -z $running_image ]]; then
            echo "  warning: cannot read the image that $service runs: $image:deployed still names the previous image"
            continue
        fi
    fi
    run docker tag "$running_image" "$image:deployed" \
        || echo "  warning: $image:deployed still names the previous image"
done

STEP=apk
say "8. Android app"
if ((BUILD_APK)); then
    run scripts/build-apk.sh
    # The app offers the update from what /api/health reports of the published APK: the release,
    # or in a rehearsal the dev app, a development build, whose version build-apk.sh published.
    apk_version=$VERSION
    if ((DRY_RUN)); then
        echo "  would check that http://127.0.0.1:$API_PORT/api/health offers the APK ${REHEARSAL:+(the dev app) }$apk_version"
    else
        if [[ -n $REHEARSAL ]]; then
            apk_version=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["version_name"])' \
                "$DATA_DIR/app/scanmylib.json") || die "cannot read the version of the dev app in $DATA_DIR/app/scanmylib.json"
        fi
        offered=$(curl -fsS --max-time 5 "http://127.0.0.1:$API_PORT/api/health" \
            | python3 -c 'import json, sys; print((json.load(sys.stdin).get("apk") or {}).get("version"))') \
            || die "the api does not answer on http://127.0.0.1:$API_PORT/api/health"
        [[ $offered == "$apk_version" ]] \
            || die "the api offers the APK '$offered', not $apk_version (see $DATA_DIR/app/scanmylib.json)"
        echo "  the api offers the APK $offered to the phones"
    fi
else
    echo "  skipped (no --apk)"
fi

STEP='done'
if ((DRY_RUN)); then
    if ((${#problems[@]})); then
        printf '\nDry run: a real run would refuse to deploy:\n'
        printf '  - %s\n' "${problems[@]}"
        exit 1
    fi
    printf '\nDry run: nothing was changed.\n'
else
    printf '\nDeployed %s %s (%s).\n' "$PROJECT" "$VERSION" "${head_commit:0:12}"
    [[ -n $BACKUP ]] && echo "Backup of the state before the restart: $BACKUP"
    print_replaced_sandbox
    echo "Log: $LOG"
fi
