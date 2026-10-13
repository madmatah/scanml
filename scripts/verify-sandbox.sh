#!/usr/bin/env bash
# Prove that the running OCR sandbox is isolated (see docs/SECURITY.md).
#
# Most checks run INSIDE the "ocr" container (docker exec), as the sandbox's own
# user, i.e. with exactly what Paddle/vLLM code could do: network reachability,
# visible files and sockets, write access, devices, namespaces, Linux
# capabilities. More read the container's configuration from the host (docker
# inspect): mounts, namespaces, security options, resource limits.
#
# Prints one PASS/FAIL line per check and exits 1 if any check fails.
#
# usage: scripts/verify-sandbox.sh [container]
# By default it checks the OCR service of the stack of this checkout's .env
# (COMPOSE_PROJECT_NAME): the sandbox ("ocr"). A development stack may run the
# fake OCR ("ocr-fake") instead, which gets the same checks except those of the
# sandbox's own directories (it only sees the socket dir); production never: a
# production stack without a running sandbox fails. The expected mount sources
# come from DATA_DIR and SANDBOX_DIR in .env (never from the environment).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/common.sh
source "$ROOT/scripts/lib/common.sh"
if [[ ! -f "$ROOT/.env" ]]; then
  echo "FAIL: no $ROOT/.env (scripts/dev-env.sh in a worktree, scripts/setup.sh in production)"
  exit 1
fi
load_env "$ROOT/.env" STACK
production=0
[[ "${STACK[COMPOSE_PROJECT_NAME]:-}" == "$PRODUCTION_PROJECT" ]] && production=1

running() { [[ -n "$1" && "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" == true ]]; }
compose_ps() { compose ps -q "$1" 2>/dev/null || true; }
container="${1:-}"
if [[ -z "$container" ]]; then
  container="$(compose_ps ocr)"
  # Only a development stack may run the fake OCR instead of the sandbox.
  if ! running "$container" && ((!production)); then container="$(compose_ps ocr-fake)"; fi
fi
if ! running "$container"; then
  if ((production)); then
    echo "FAIL: production's OCR sandbox (ocr) is not running"
  else
    echo "FAIL: no OCR container is running (scripts/dev.sh up)"
  fi
  exit 1
fi
# The fake OCR (api image, development) has no sandbox directory, no GPU and no "ocr" user.
kind=sandbox
[[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$container")" == ocr-fake ]] && kind=fake
if [[ $kind == fake ]] && ((production)); then
  echo "FAIL: $container is the fake OCR: production must run the OCR sandbox"
  exit 1
fi

# The LAN address the phone uses to reach this PC (PUBLIC_URL in .env).
public_url="${STACK[PUBLIC_URL]:-}"
api_port="${STACK[API_PORT]:-}"
lan_ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}')"
lan_target="$(sed -E 's#^[a-z]+://([^/]+).*#\1#' <<<"${public_url:-http://${lan_ip:-192.168.1.10}:${api_port:-8765}}")"
data_dir="${STACK[DATA_DIR]:-}"
sandbox_dir="${STACK[SANDBOX_DIR]:-}"

failures=0
check() {  # check <description> <expected> <actual>
  if [[ "$2" == "$3" ]]; then
    echo "PASS: $1"
  else
    echo "FAIL: $1 (expected '$2', got '$3')"
    failures=$((failures + 1))
  fi
}

echo "== container configuration (docker inspect $(docker inspect -f '{{.Name}}' "$container" | tr -d /))"
[[ $kind == fake ]] && echo "INFO: fake OCR of a development stack (not the sandbox)"
inspect() { docker inspect -f "$1" "$container"; }
check "network mode is none" "none" "$(inspect '{{.HostConfig.NetworkMode}}')"
check "root filesystem is read-only" "true" "$(inspect '{{.HostConfig.ReadonlyRootfs}}')"
check "not privileged" "false" "$(inspect '{{.HostConfig.Privileged}}')"
check "all capabilities dropped" '["ALL"]' "$(inspect '{{json .HostConfig.CapDrop}}')"
check "no capability added" "null" "$(inspect '{{json .HostConfig.CapAdd}}')"
check "no-new-privileges set" "yes" "$(inspect '{{json .HostConfig.SecurityOpt}}' | grep -q 'no-new-privileges' && echo yes || echo no)"
check "no seccomp, AppArmor or SELinux exemption" "" \
  "$(inspect '{{json .HostConfig.SecurityOpt}}' | grep -oE '[a-z]+[=:]unconfined|label[=:]disable' | tr '\n' ' ' || true)"
check "/proc paths masked and read-only (no systempaths=unconfined)" "yes" \
  "$(inspect '{{len .HostConfig.MaskedPaths}} {{json .HostConfig.ReadonlyPaths}}' | grep -qE '^[1-9][0-9]* .*"/proc/sys"' && echo yes || echo no)"
check "own PID namespace" "" "$(inspect '{{.HostConfig.PidMode}}')"
ipc_mode="$(inspect '{{.HostConfig.IpcMode}}')"
check "own IPC namespace (not the host's or another container's)" "yes" \
  "$([[ $ipc_mode =~ ^(private|shareable|none)$ ]] && echo yes || echo "no ($ipc_mode)")"
check "own UTS namespace" "" "$(inspect '{{.HostConfig.UTSMode}}')"
check "own cgroup namespace" "private" "$(inspect '{{.HostConfig.CgroupnsMode}}')"
devices="$(inspect '{{json .HostConfig.Devices}}')"
check "no host device passed (the GPU comes through CDI)" "yes" \
  "$([[ $devices == null || $devices == "[]" ]] && echo yes || echo "no ($devices)")"
cgroup_rules="$(inspect '{{json .HostConfig.DeviceCgroupRules}}')"
check "no extra device cgroup rule" "yes" \
  "$([[ $cgroup_rules == null || $cgroup_rules == "[]" ]] && echo yes || echo "no ($cgroup_rules)")"
echo "INFO: device requests: $(inspect '{{range .HostConfig.DeviceRequests}}{{.Driver}}:{{join .DeviceIDs ","}} {{end}}')"

# Every Docker mount, compared with the three the sandbox needs.
mounts="$(inspect '{{range .Mounts}}{{.Type}}|{{.Source}}|{{.Destination}}|{{if .RW}}rw{{else}}ro{{end}}{{"\n"}}{{end}}' | sed '/^$/d')"
echo "INFO: mounts: $(tr '\n' ' ' <<<"$mounts")"
check "no host bind mount from /home" "" "$(cut -d'|' -f2 <<<"$mounts" | grep '^/home' || true)"
actual="$(while IFS='|' read -r type source destination mode; do
  if [[ -n "$type" ]]; then echo "$type|$(realpath -m "${source:-/}")|$destination|$mode"; fi
done <<<"$mounts" | sort)"
if [[ $kind == fake && -n "$data_dir" ]]; then
  check "mounts are exactly DATA_DIR/run" "bind|$(realpath -m "$data_dir/run")|/run/scanmylib|rw " \
    "$(tr '\n' ' ' <<<"$actual")"
elif [[ $kind == sandbox && -n "$data_dir" && -n "$sandbox_dir" ]]; then
  expected="$(printf '%s\n' "bind|$(realpath -m "$sandbox_dir")|/opt/sandbox|ro" \
    "bind|$(realpath -m "$data_dir/run")|/run/scanmylib|rw" \
    "bind|$(realpath -m "$data_dir/ocr-cache")|/var/cache/ocr|rw" | sort)"
  check "mounts are exactly SANDBOX_DIR (ro), DATA_DIR/run and DATA_DIR/ocr-cache" \
    "$(tr '\n' ' ' <<<"$expected")" "$(tr '\n' ' ' <<<"$actual")"
else
  check "DATA_DIR and SANDBOX_DIR set in .env" "yes" "no"
fi

pids_limit="$(inspect '{{if .HostConfig.PidsLimit}}{{.HostConfig.PidsLimit}}{{end}}')"
check "process count limited (pids_limit)" "yes" "$([[ $pids_limit =~ ^[1-9][0-9]*$ ]] && echo yes || echo no)"
memory_limit="$(inspect '{{.HostConfig.Memory}}')"
check "memory limited (mem_limit)" "yes" "$([[ $memory_limit =~ ^[1-9][0-9]*$ ]] && echo yes || echo no)"
log_driver="$(inspect '{{.HostConfig.LogConfig.Type}}')"
log_max_size="$(inspect '{{index .HostConfig.LogConfig.Config "max-size"}}')"
check "container log size bounded (logging max-size)" "yes" \
  "$([[ $log_driver != json-file || -n $log_max_size ]] && echo yes || echo "no ($log_driver without max-size)")"

echo "== inside the sandbox (docker exec, as the sandbox user)"
set +e
docker exec -i -e LAN_TARGET="$lan_target" -e HOST_HOME="$(getent passwd "$(id -u)" | cut -d: -f6)" -e SANDBOX_KIND="$kind" "$container" python3 - <<'PY'
import errno
import os
import re
import socket
import stat
import sys

failures = 0


def check(description: str, ok: bool, detail: str = "") -> None:
    global failures
    print(f"{'PASS' if ok else 'FAIL'}: {description}" + (f" ({detail})" if detail else ""))
    failures += not ok


interfaces = sorted(os.listdir("/sys/class/net"))
check("only the loopback network interface", interfaces == ["lo"], ", ".join(interfaces))

try:
    addresses = socket.getaddrinfo("example.com", 443)
    check("DNS resolution fails", False, f"example.com -> {addresses[0][4][0]}")
except socket.gaierror as exc:
    check("DNS resolution fails", True, exc.strerror)

lan_host, _, lan_port = os.environ["LAN_TARGET"].rpartition(":")
for host, port in (("1.1.1.1", 443), (lan_host, int(lan_port)), ("172.17.0.1", 80)):
    try:
        with socket.create_connection((host, port), timeout=3):
            check(f"outbound TCP to {host}:{port} fails", False, "connected")
    except OSError as exc:
        check(f"outbound TCP to {host}:{port} fails", True, exc.strerror or str(exc))

host_home = os.environ["HOST_HOME"]
check(f"{host_home} (host home) is not visible", not os.path.exists(host_home))

# Mount table: mount point -> (root within its filesystem, options, type).
mounts = {}
with open("/proc/self/mountinfo") as table:
    for line in table:
        fields, _, filesystem = line.rstrip("\n").partition(" - ")
        fields = fields.split()
        point = fields[4].encode().decode("unicode_escape")  # \040 for spaces...
        mounts[point] = {"root": fields[3], "options": fields[5].split(","), "type": filesystem.split()[0]}

PSEUDO = {"proc", "sysfs", "cgroup", "cgroup2", "devpts", "mqueue"}
SANDBOX = os.environ["SANDBOX_KIND"] == "sandbox"  # else the fake OCR: the socket dir only
HOST_DIRS = {"/opt/sandbox", "/run/scanmylib", "/var/cache/ocr"} if SANDBOX else {"/run/scanmylib"}
WRITABLE_DIRS = sorted(HOST_DIRS - {"/opt/sandbox"})
OWN_TMPFS = {"/tmp", "/dev", "/dev/shm"}  # fresh tmpfs mounts made by Docker for the container


def own_tmpfs(point: str, mount: dict) -> bool:
    return mount["type"] == "tmpfs" and mount["root"] == "/" and point in OWN_TMPFS


def cdi_scratch(point: str) -> bool:
    """Scratch files of the NVIDIA container toolkit (a tmpfs of its own, nothing from the host)."""
    return point.startswith("/run/nvidia-ctk-hook") or point == "/proc/driver/nvidia/params"


def masked(mount: dict) -> bool:
    """A /proc or /sys entry hidden by binding /dev/null over it."""
    return mount["root"] == "/null"


def read_only(mount: dict) -> bool:
    return "ro" in mount["options"]


# Host files mounted by the GPU runtime (driver libraries, nvidia-smi) and by
# Docker (/etc/hosts...) are single read-only files; host directories must be ours.
unexpected_dirs = sorted(
    point
    for point, mount in mounts.items()
    if os.path.isdir(point)
    and point != "/"
    and point not in HOST_DIRS
    and mount["type"] not in PSEUDO
    and not own_tmpfs(point, mount)
    and not cdi_scratch(point)
    and not (point.startswith(("/proc/", "/sys/")) and read_only(mount))
)
check(
    f"no directory mount besides {', '.join(sorted(HOST_DIRS))} (and the container's /tmp, /dev, /dev/shm)",
    not unexpected_dirs,
    ", ".join(unexpected_dirs),
)
host_files_rw = sorted(
    p for p, m in mounts.items() if os.path.isfile(p) and not read_only(m) and not cdi_scratch(p) and not masked(m)
)
check("host files mounted (driver libraries, /etc/hosts...) are read-only", not host_files_rw, ", ".join(host_files_rw))

# Whatever the filesystem type: a writable bind of a host tmpfs (/run/user/...,
# /dev/shm) is as dangerous as one of a disk directory.
other_writable = sorted(
    point
    for point, mount in mounts.items()
    if not read_only(mount)
    and point not in (*WRITABLE_DIRS, "/proc", "/dev/pts", "/dev/mqueue")
    and not own_tmpfs(point, mount)
    and not cdi_scratch(point)
    and not masked(mount)
)
check(
    f"only {' and '.join(WRITABLE_DIRS)} {'are' if len(WRITABLE_DIRS) > 1 else 'is'} writable host storage"
    " (besides the container's tmpfs)",
    not other_writable,
    ", ".join(other_writable),
)

# A Unix socket stays connectable through a read-only mount (docker.sock!).
ALLOWED_SOCKETS = {"/run/nvidia-persistenced/socket"}  # part of the NVIDIA CDI spec
sockets = []
for point in mounts:
    try:
        if stat.S_ISSOCK(os.stat(point).st_mode):
            sockets.append(point)
    except OSError:
        pass
unexpected_sockets = sorted(set(sockets) - ALLOWED_SOCKETS)
check("no host socket mounted (docker.sock, agents...)", not unexpected_sockets, ", ".join(unexpected_sockets))
for point in sorted(set(sockets) & ALLOWED_SOCKETS):
    print(f"INFO: host socket reachable from the sandbox: {point} (NVIDIA container toolkit)")


def write_fails_read_only(directory: str) -> None:
    probe = os.path.join(directory, f".write-probe-{os.getpid()}")
    try:
        with open(probe, "w"):
            pass
        os.unlink(probe)
        check(f"writing to {directory} fails (read-only)", False, "write succeeded")
    except OSError as exc:
        check(f"writing to {directory} fails (read-only)", exc.errno == errno.EROFS, exc.strerror)


check("root filesystem mounted read-only", read_only(mounts["/"]), ",".join(mounts["/"]["options"]))
# Owned by the container's user: only the read-only mount stops it.
write_fails_read_only(os.path.expanduser("~ocr") if SANDBOX else "/state")
if SANDBOX:
    check("/opt/sandbox mounted read-only", "/opt/sandbox" in mounts and read_only(mounts["/opt/sandbox"]))
    write_fails_read_only("/opt/sandbox")  # owned by the sandbox user on the host

for point in ("/proc/sys", "/proc/sysrq-trigger", "/sys", "/sys/fs/cgroup"):
    check(f"{point} mounted read-only", point in mounts and read_only(mounts[point]), "not a separate mount" if point not in mounts else "")
unmasked = [path for path in ("/proc/kcore", "/proc/keys", "/proc/timer_list") if os.path.exists(path) and path not in mounts]
check("sensitive /proc files are masked", not unmasked, ", ".join(unmasked))

devices = []
for directory, _, names in os.walk("/dev"):
    for name in names:
        path = os.path.join(directory, name)
        mode = os.lstat(path).st_mode
        if stat.S_ISCHR(mode) or stat.S_ISBLK(mode):
            devices.append(path)
BASIC_DEVICES = {"/dev/null", "/dev/zero", "/dev/full", "/dev/random", "/dev/urandom", "/dev/tty", "/dev/console", "/dev/ptmx"}
extra_devices = sorted(d for d in devices if d not in BASIC_DEVICES and not d.startswith(("/dev/pts/", "/dev/nvidia", "/dev/dri/")))
check("no device besides null/zero/random/tty and the GPU", not extra_devices, ", ".join(extra_devices))

# The kernel's initial namespaces have fixed inode numbers (include/linux/proc_ns.h).
for name, host_inode in (("ipc", 0xEFFFFFFF), ("uts", 0xEFFFFFFE), ("pid", 0xEFFFFFFC), ("cgroup", 0xEFFFFFFB)):
    if os.path.exists(f"/proc/self/ns/{name}"):
        check(f"{name} namespace is not the host's", os.stat(f"/proc/self/ns/{name}").st_ino != host_inode)

with open("/proc/self/status") as status_file:
    status = dict(line.rstrip("\n").split(":\t", 1) for line in status_file if ":\t" in line)
for key in ("CapEff", "CapPrm", "CapBnd"):
    check(f"{key} = 0 (no capabilities)", int(status[key], 16) == 0, status[key])
check("NoNewPrivs = 1", status["NoNewPrivs"] == "1", status["NoNewPrivs"])
check("seccomp filter active", status["Seccomp"] == "2", status["Seccomp"])
try:
    with open("/sys/module/apparmor/parameters/enabled") as flag:
        apparmor = flag.read().strip() == "Y"
except OSError:
    apparmor = False
if apparmor:
    attr = "/proc/self/attr/apparmor/current"
    with open(attr if os.path.exists(attr) else "/proc/self/attr/current") as current:
        profile = current.read().strip("\x00\n ")
    check("AppArmor profile enforced", profile.endswith("(enforce)"), profile)
else:
    print("INFO: AppArmor is not enabled on this host")
check("not running as root", os.getuid() != 0 and os.geteuid() != 0, f"uid={os.getuid()}")

# The environment every sandbox process starts with (that of the container's init).
with open("/proc/1/environ", "rb") as environ:
    variables = dict(item.split("=", 1) for item in environ.read().decode(errors="replace").split("\0") if "=" in item)
secret_like = sorted(n for n in variables if re.search(r"TOKEN|SECRET|PASSW|CREDENTIAL|AUTH|API_?KEY|ACCESS_?KEY|PRIVATE", n, re.I))
check("no credential-like environment variable", not secret_like, ", ".join(secret_like))
host_paths = sorted(n for n, value in variables.items() if host_home in value)
check(f"no environment variable mentions {host_home}", not host_paths, ", ".join(host_paths))

socket_path = os.environ.get("OCR_SOCKET", "/run/scanmylib/ocr.sock")
if os.path.exists(socket_path):
    mode = os.stat(socket_path).st_mode & 0o777
    check("API socket is not world-accessible", mode & 0o007 == 0, oct(mode))

sys.exit(1 if failures else 0)
PY
inside=$?
set -e

if (( failures > 0 || inside != 0 )); then
  echo "RESULT: FAIL"
  exit 1
fi
echo "RESULT: all checks passed"
