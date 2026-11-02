# shellcheck shell=bash
# The check of the engine's environment in a new ocr container, shared by the scripts that start
# one (sourced after scripts/lib/common.sh, whose compose() it runs), and in a container of its own
# before a restart.

# Above the bound that the check sets itself (CHECK_TIMEOUT_SECONDS in
# ocr/scanmylib_ocr/engine_environment.py, and the time to stop its worker), so that docker exec ends
# even when the container no longer answers: the two change together.
readonly ENGINE_CHECK_BOUND_SECONDS=330

# Nothing the check prints reaches the terminal or a log: what the sandbox prints is untrusted, and a
# terminal interprets its control sequences.
check_engine_environment() { # check_engine_environment CONTAINER
    local container=$1
    local engine_check=(timeout --kill-after=10 "$ENGINE_CHECK_BOUND_SECONDS" docker exec "$container" python3 -m
        scanmylib_ocr.engine_environment)
    printf '  $'
    printf ' %q' "${engine_check[@]}"
    printf '\n'
    "${engine_check[@]}" > /dev/null 2>&1
}

# The same check, before the restart, in a container of its own: the new image imports the engine's libraries from
# SANDBOX, so that an image that cannot run the sandbox is refused while production still runs. No engine code runs
# here ahead of an isolation check, so the container keeps the isolation of the ocr service without one: no network, a
# read-only root filesystem, tmpfs for what it writes, no capabilities, no-new-privileges, a non-root user, and only
# the sandbox mounted, read-only. The GPU is there because the engine's libraries may link the driver's libraries that
# CDI mounts, as they do in the service; the check hides it from the worker. OPTIONS are those of the service
# (scripts/lib/stack.py sandbox-check-options).
build_sandbox_check() { # build_sandbox_check ARRAY NAME IMAGE SANDBOX USER [OPTION...]
    local -n _check=$1
    local name=$2 image=$3 sandbox=$4 user=$5
    shift 5
    _check=(docker run --rm --init --name "$name" --network none --read-only --tmpfs /tmp
        --tmpfs /var/cache/ocr:mode=1777 --cap-drop ALL --security-opt no-new-privileges:true --user "$user"
        --device nvidia.com/gpu=all "$@" --mount "type=bind,src=$sandbox,dst=/opt/sandbox,readonly" "$image"
        python3 -m scanmylib_ocr.engine_environment)
}

# timeout ends only the docker CLI: the container it leaves is removed by its name.
run_sandbox_check() { # run_sandbox_check NAME COMMAND...
    local name=$1 status=0
    shift
    printf '  $ timeout --kill-after=10 %s' "$ENGINE_CHECK_BOUND_SECONDS"
    printf ' %q' "$@"
    printf '\n'
    timeout --kill-after=10 "$ENGINE_CHECK_BOUND_SECONDS" "$@" > /dev/null 2>&1 || status=$?
    if ((status)); then
        docker rm -f "$name" > /dev/null 2>&1 || true
    fi
    return "$status"
}

# What shows why a check that build_sandbox_check built failed, in one command, since scripts/prod.sh runs no
# container: through cat -v, so that no control sequence of the sandbox reaches the terminal.
print_sandbox_check_diagnostic() { # print_sandbox_check_diagnostic COMMAND...
    printf ' '
    printf ' %q' "$@"
    printf ' 2>&1 | cat -v\n'
}

# One copy of the commands that show why the check failed: scripts/prod.sh's allowlist must accept them.
print_engine_check_steps() { # print_engine_check_steps COMPOSE_HINT SERVICE
    local hint=$1 service=$2
    echo "  $hint start $service"
    echo "  $hint exec -T $service python3 -m scanmylib_ocr.engine_environment 2>&1 | cat -v"
    echo "  $hint stop $service"
}

# No page may reach an OCR service that failed a check.
stop_ocr_service() { # stop_ocr_service COMPOSE_HINT SERVICE REASON
    local hint=$1 service=$2 reason=$3
    echo "  stopping $service, $reason"
    compose stop "$service" || echo "  could not stop it: $hint stop $service"
}
