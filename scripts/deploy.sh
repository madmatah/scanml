#!/usr/bin/env bash
# Deploys a published release to production: the only way production changes (see CLAUDE.md).
#
# Usage: scripts/deploy.sh [--dry-run] [--skip-tests] [--apk] [--first-install] [--allow-downgrade]
#   --dry-run        check the preconditions and print every step without doing it
#   --skip-tests     skip the server, web UI and OCR unit tests
#   --apk            also build and publish the release APK (scripts/build-apk.sh)
#   --first-install  production has no database yet (DATA_DIR/state/scanmylib.db)
#   --allow-downgrade  deploy a release older than the one production runs, whose api must read
#                    the database as the newer release left it
#
# Preconditions, all checked before anything changes, under a lock (one deploy at a time from a
# checkout): run from production's checkout (the project directory of production's containers,
# else ~/Dev/scanmylib: scripts/lib/stack.py), clean (untracked files included, and no file marked
# assume-unchanged or skip-worktree, which git status would not compare), on a published release:
# HEAD is the commit of the tag vVERSION on origin (git ls-remote), which .github/workflows/release.yml
# created (git checkout vX.Y.Z); production's .env, in the strict format of scripts/lib/stack.py,
# with production's identity (COMPOSE_PROJECT_NAME=scanmylib, the OCR sandbox, the release app),
# an existing DATA_DIR holding production's database (unless --first-install), an existing
# LIBRARY_DIR and an installed OCR sandbox; in a real run, the running api (/api/health) not on a
# newer release, unless --allow-downgrade. It never tags: releases are published on GitHub, and
# each installation deploys the ones it wants.
#
# The commit is exported first (git archive HEAD), and every docker compose call reads the
# compose.yaml of that export, so that nothing uncommitted, ignored or untracked is checked, built
# or started: the images are built from the export, and the containers are started with this
# checkout as project directory (production's containers record it: scripts/lib/stack.py).
#
# Steps:
#   1. images: api and ocr built from the export; the running containers are not touched. The
#      images production runs keep the tag <prefix>-<service>:deployed (the images of its
#      containers get it whenever it names another, e.g. on the first run, or after a deploy that
#      failed once the containers were recreated): rebuilding moves :latest, and docker then
#      forgets the previous image unless a tag still names it
#   2. unit tests of the new code and images: server (pytest in the api test image), web UI (node
#      --test), OCR (unittest in the new ocr image). If anything fails up to step 3, :latest goes
#      back to :deployed: production is unchanged
#   3. backup of DATA_DIR/state (without its thumbnail cache) into
#      DATA_DIR/backups/state-<time>-v<version>/, the database copied with SQLite's online backup
#      (consistent while the api runs) and checked, right before the restart (what changes in the
#      seconds between the two is not in it); the 10 most recent backups are kept
#   4. restart: docker compose up -d api ocr, waiting until both are healthy and the api reports
#      VERSION
#   5. scripts/verify-sandbox.sh; if it fails, the OCR service is stopped. Once it passes, the new
#      images become :deployed: production runs them
#   6. with --apk: scripts/build-apk.sh (tests, release build, lint, signing, publication), then a check
#      that /api/health offers the published APK
# A real run ignores SIGHUP (a lost terminal does not stop it halfway) and is also logged to
# DATA_DIR/logs/deploy-<time>.log. On failure, it says what state production is in after the
# step that failed, and how to roll back (the :deployed images, the backup of the state).
#
# Rehearsal on a throwaway stack: SCANMYLIB_DEPLOY_REHEARSAL=<project> deploys the .env of this
# checkout instead, when its COMPOSE_PROJECT_NAME is <project> and the export passes the isolation
# check of scripts/dev.sh. The git checks are then only reported, and HEAD need not be a release
# (it is still what is checked, built and started: commit first), the fake OCR is allowed
# (OCR_SERVICE=ocr-fake), and the app is the dev one.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=lib/common.sh
source "$ROOT/scripts/lib/common.sh"

usage() { sed -n '/^# Usage:/,/^#   *the database as/{s/^# \{0,1\}//;p}' "${BASH_SOURCE[0]}" >&2; exit 2; }

DRY_RUN=0 SKIP_TESTS=0 BUILD_APK=0 FIRST_INSTALL=0 ALLOW_DOWNGRADE=0
for arg in "$@"; do
    case $arg in
        --dry-run) DRY_RUN=1 ;;
        --skip-tests) SKIP_TESTS=1 ;;
        --apk) BUILD_APK=1 ;;
        --first-install) FIRST_INSTALL=1 ;;
        --allow-downgrade) ALLOW_DOWNGRADE=1 ;;
        *) usage ;;
    esac
done
REHEARSAL=${SCANMYLIB_DEPLOY_REHEARSAL:-}
ENV_FILE=$ROOT/.env
readonly KEEP_BACKUPS=10
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
fail() { printf '  FAIL  %s\n' "$*"; problems+=("$*"); }
# A git precondition: enforced in production, only reported in a rehearsal.
git_fail() { if [[ -n $REHEARSAL ]]; then printf '  warn  %s (rehearsal: not enforced)\n' "$*"; else fail "$*"; fi; }

say "Preconditions${REHEARSAL:+ (rehearsal on $REHEARSAL)}"
head_commit=$(git rev-parse HEAD)
# The commit, whose compose.yaml every docker compose call below reads.
EXPORT=$(mktemp -d "${TMPDIR:-/tmp}/scanmylib-deploy.XXXXXX")
trap 'rm -rf -- "$EXPORT"' EXIT
chmod 755 "$EXPORT"
git archive --format=tar "$head_commit" | tar --extract --file - -C "$EXPORT"
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
    printf '  skip  the release on origin (rehearsal: no network, and any commit)\n'
elif ! ((read_origin)); then
    printf '  skip  the release on origin (not production'"'"'s checkout)\n'
# Read on origin itself, in a dry run as in a real one: nothing local is trusted or updated.
elif release_error=$(release_problem "$ROOT"); then
    pass "the release v$(git show HEAD:VERSION | tr -d '[:space:]'), as published on origin (${head_commit:0:12})"
else
    fail "$release_error"
fi

declare -A STACK=()
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
UID_GID="${STACK[SCANMYLIB_UID]:-$(id -u)}:${STACK[SCANMYLIB_GID]:-$(id -g)}"

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
        [[ -n ${STACK[SANDBOX_SETUP_DIR]:-} ]] \
            || info "no SANDBOX_SETUP_DIR in .env: ocr-setup cannot reinstall the sandbox (add SANDBOX_SETUP_DIR=$SANDBOX_DIR)"
    elif [[ $REHEARSAL == "$PRODUCTION_PROJECT" ]]; then
        fail "SCANMYLIB_DEPLOY_REHEARSAL cannot be the production project"
    elif [[ $PROJECT != "$REHEARSAL" ]]; then
        fail "COMPOSE_PROJECT_NAME in .env is '${PROJECT:-unset}', not the rehearsal project $REHEARSAL"
    # Checked twice: as the build resolves it (the export as project directory) and as up, ps and
    # stop resolve it (this checkout as project directory: relative extends files and bind sources
    # are read from this checkout, uncommitted changes included).
    elif isolation=$( (COMPOSE_ROOT=$EXPORT assert_isolated_from_production "$ENV_FILE") 2>&1 \
        && (assert_isolated_from_production "$ENV_FILE") 2>&1 ); then
        pass "the rehearsal stack $PROJECT shares nothing with production"
    else
        fail "the rehearsal stack is not isolated from production:"
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
    # The sandbox runs the OCR, and its venv runs the OCR unit tests.
    if [[ $OCR_SERVICE == ocr ]] || ! ((SKIP_TESTS)); then
        if [[ -f $SANDBOX_DIR/MANIFEST.json ]]; then
            pass "OCR sandbox installed in $SANDBOX_DIR"
        else
            fail "no OCR sandbox in SANDBOX_DIR ('$SANDBOX_DIR'): scripts/setup.sh installs it"
        fi
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

STAMP=$(date +%Y%m%d-%H%M%S)
STEP=preconditions BACKUP= previous_version= tee_pid=
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

# Runs a command, or only prints it in a dry run.
run() {
    local shown=("$@") hint
    if [[ $1 == compose ]]; then
        read -ra hint <<< "$COMPOSE_HINT"
        shown=("${hint[@]}" "${@:2}")
    fi
    printf '  %s' "$( ((DRY_RUN)) && echo 'would run:' || echo '$')"
    printf ' %q' "${shown[@]}"
    printf '\n'
    ((DRY_RUN)) || "$@"
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

on_exit() {
    local status=$?
    if [[ -n $EXPORT ]]; then rm -rf -- "$EXPORT"; fi
    if ((status)) && [[ $STEP != done ]]; then
        printf '\nDEPLOY FAILED during the step "%s" (exit %s).\n' "$STEP" "$status"
        case $STEP in
            preconditions) ;;
            images | tests | backup)
                restore_deployed_images
                echo "$WHO is unchanged: the previous containers still run, and the image tags point to the"
                echo "previous images again. Fix the problem, then deploy again."
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
            apk)
                echo "$WHO runs $VERSION (healthy, sandbox isolated, its images tagged :deployed); the APK was"
                echo "not published, or the api does not offer it to the phones (its metadata, scanmylib.json):"
                echo "the phones keep the previous app. Fix the problem, then run scripts/build-apk.sh here"
                echo "(or roll back)."
                [[ -n $BACKUP ]] && echo "Backup of the state before the restart: $BACKUP"
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
COMPOSE_ROOT=$EXPORT run compose build api ocr

STEP=tests
say "2. Unit tests of the new code and images"
if ((SKIP_TESTS)); then
    echo "  skipped (--skip-tests)"
else
    run docker build --target test -t "$IMAGE_PREFIX-api:test" "$EXPORT/server"
    run docker run --rm --name "$IMAGE_PREFIX-deploy-pytest-$$" --network none --read-only --tmpfs /tmp \
        "$IMAGE_PREFIX-api:test"
    run docker run --rm --pull never --name "$IMAGE_PREFIX-deploy-webtest-$$" --network none --read-only \
        --user "$(id -u):$(id -g)" -v "$EXPORT/server/scanmylib/web:/web:ro" \
        node:22-bookworm-slim node --test '/web/tests/*.test.js'
    run docker run --rm --pull never --name "$IMAGE_PREFIX-deploy-ocrtest-$$" --init --network none --read-only \
        --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true --user "$UID_GID" \
        -v "$EXPORT/ocr:/app:ro" -v "$SANDBOX_DIR:/opt/sandbox:ro" \
        "$IMAGE_PREFIX-ocr:latest" /opt/sandbox/venv-paddle/bin/python -m unittest discover -s /app/tests
fi

STEP=backup
say "3. Backup of the state"
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

STEP=restart
say "4. Restart"
if ((DRY_RUN)); then
    echo "  would read the version of the running api (http://127.0.0.1:$API_PORT/api/health)"
else
    previous_version=$(curl -fsS --max-time 3 "http://127.0.0.1:$API_PORT/api/health" 2> /dev/null \
        | python3 -c 'import json, sys; print(json.load(sys.stdin).get("version", ""))' 2> /dev/null || true)
    [[ -n $previous_version ]] && info "the running api reports version $previous_version"
fi
# Created here, before Docker would create missing bind-mount sources as root.
run mkdir -p "$DATA_DIR/state" "$DATA_DIR/run" "$DATA_DIR/ocr-cache" "$DATA_DIR/app" "$LIBRARY_DIR"
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
say "5. Sandbox isolation"
if ((DRY_RUN)); then
    echo "  would run: scripts/verify-sandbox.sh on the $OCR_SERVICE container (and stop it if it fails)"
elif ! scripts/verify-sandbox.sh "$(compose ps -q "$OCR_SERVICE" 2> /dev/null || true)"; then
    echo "  stopping $OCR_SERVICE, which failed the isolation check"
    compose stop "$OCR_SERVICE" || echo "  could not stop it: $COMPOSE_HINT stop $OCR_SERVICE"
    die "scripts/verify-sandbox.sh failed"
fi
# Production runs the new images: they are now the ones to put back.
for service in api ocr; do
    run docker tag "$IMAGE_PREFIX-$service:latest" "$IMAGE_PREFIX-$service:deployed" \
        || echo "  warning: $IMAGE_PREFIX-$service:deployed still names the previous image"
done

STEP=apk
say "6. Android app"
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

STEP=done
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
    echo "Log: $LOG"
fi
