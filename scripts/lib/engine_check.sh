# shellcheck shell=bash
# The check of the engine's environment in a new ocr container, shared by the scripts that start
# one (sourced after scripts/lib/common.sh, whose compose() it runs).

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
