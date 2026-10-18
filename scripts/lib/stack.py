#!/usr/bin/env python3
"""The .env of a ScanMyLib stack, production's checkout, and the isolation of a stack from production.

Shared by the scripts: scripts/lib/common.sh runs it, scripts/e2e_test.py imports it. Standard
library only, so that it runs with the host's python3.

What these checks are for
-------------------------
They protect production from misconfiguration, from mistakes in a branch (a wrong .env, a
compose.yaml change, a command typed in the wrong checkout) and from compromised build
dependencies (code that runs inside the containers a branch builds). They do not claim to stop a
deliberately malicious branch: its scripts run as the user, with the user's rights.

The .env format
---------------
docker compose and the scripts read a .env the same way only if it keeps to a strict format,
which every script enforces (a .env that breaks it is refused, never interpreted):

* blank lines, and comment lines whose first character is "#";
* KEY=VALUE lines: KEY made of capital letters, digits and "_", starting with a letter; VALUE
  made of letters, digits and the characters _ . / : @ % + , - only, so no spaces, quotes, "$",
  "#" or backslashes, which docker compose would interpret (comments after a value, variable
  substitution, escapes...);
* each KEY at most once, UTF-8, LF line endings;
* no COMPOSE_* key besides COMPOSE_PROJECT_NAME, and no DOCKER_* or BUILDKIT_* key: they would
  change which files, profiles or daemon docker compose uses.

Production's checkout
---------------------
Production runs from one checkout: the project directory of its containers (the label
com.docker.compose.project.working_dir that docker compose gives them) or, when it has no
container (first installation), ~/Dev/scanmylib. A clone or a worktree holding a copy of
production's .env is not production. The home directory is the user's entry in the password
database, never $HOME, which can point elsewhere.

Isolation from production
-------------------------
`check-isolation` reads what docker compose resolves for a stack (`docker compose config --format
json`, every profile, and the same without interpolation, which keeps env_file and label_file:
the first merges them into the settings) together with the .env of the stack, and refuses:

* production's project, images and published ports. Image names are compared as Docker reads
  them ("scanmylib-api", "docker.io/library/scanmylib-api" and
  "index.docker.io/library/scanmylib-api:latest" are the same image), and every image must be the
  stack's own, <IMAGE_PREFIX>-api:latest or <IMAGE_PREFIX>-ocr:latest, with IMAGE_PREFIX made of
  lowercase letters, digits and "-";
* any service setting outside SERVICE_KEYS (privileged, cap_add, volumes_from, use_api_socket,
  pid, ipc, uts, userns_mode, cgroup, labels, env_file, label_file...), devices other than the
  GPU (CDI nvidia.com/gpu=...), security options other than no-new-privileges, any network_mode
  but none (or another service of the stack), networks other than the stack's own
  (<project>_...) or with a driver other than bridge, build settings outside BUILD_KEYS, build
  contexts outside the project directory, and `include` in the compose file (its env_file feeds
  host files into the interpolation of what it includes);
* host paths. The stack's DATA_DIR must be absolute, outside the system directories and your home
  directory (and $HOME), and must neither be nor contain /tmp; every other host path the stack
  uses (bind mounts, LIBRARY_DIR, ANDROID_DIR...) must be inside its DATA_DIR. No path may be,
  contain or be inside one of production's (its checkout, DATA_DIR, LIBRARY_DIR, SANDBOX_DIR,
  ANDROID_DIR and signing key, from its .env and from the defaults, and every bind mount of its
  containers). Two exceptions, read-only only: production's SANDBOX_DIR (the OCR models, mounted
  read-only by a development sandbox) and production's signing key directory
  (ANDROID_KEYSTORE_DIR, mounted read-only by the signing container of scripts/build-apk.sh). A
  bind mount whose source does not exist and that docker compose would not create (the
  placeholder of ocr-setup) is never mounted.

`check-compose-command` checks the docker compose command lines that scripts/dev.sh and
scripts/prod.sh pass on (COMPOSE_COMMANDS, COMMAND_OPTIONS).

Usage:
    stack.py env FILE
        check FILE and print its KEY=VALUE lines
    stack.py production-checkout  < [containers]
        print production's checkout
    stack.py check-isolation --env FILE --project-dir DIR --compose-file FILE
            < {"config": ..., "raw": ..., "containers": [...]}
        print what the stack shares with production (exit status 1), else nothing ("raw": the
        configuration without interpolation)
    stack.py check-paths [--runner-temp DIR] NAME=PATH...  < [containers]
        print the paths that are, contain or are inside production's, or are in your home
        directory except inside DIR (GitHub Actions' RUNNER_TEMP) (exit status 1)
    stack.py check-compose-command [--production] -- COMMAND [ARGS...]
        print why scripts/dev.sh (or scripts/prod.sh) refuses this docker compose command
(containers: `docker inspect` of production's containers, a JSON array.)
"""

from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import sys
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: What docker prints as JSON (`docker inspect`, `docker compose config`): untyped, read with defaults for every key.
JsonObject = dict[str, Any]

#: The production stack's project name (scripts/lib/common.sh, compose.yaml's COMPOSE_PROJECT_NAME).
PRODUCTION_PROJECT = "scanmylib"
#: Production's checkout when no production container names it, relative to the home directory.
DEFAULT_CHECKOUT = "Dev/scanmylib"
#: The label docker compose gives a container: the project directory it was started from.
WORKING_DIR_LABEL = "com.docker.compose.project.working_dir"

_KEY = re.compile(r"[A-Z][A-Z0-9_]*")
_VALUE = re.compile(r"[A-Za-z0-9_./:@%+,-]*")
_FORBIDDEN_KEY = re.compile(r"COMPOSE_(?!PROJECT_NAME$)|DOCKER_|BUILDKIT_")
_IMAGE_PREFIX = re.compile(r"[a-z0-9][a-z0-9-]*")

#: Host directories no stack may use, nor anything inside them.
SYSTEM_DIRS = (
    "/bin",
    "/boot",
    "/dev",
    "/etc",
    "/lib",
    "/lib32",
    "/lib64",
    "/libx32",
    "/proc",
    "/root",
    "/run",
    "/sbin",
    "/snap",
    "/sys",
    "/usr",
    "/var",
)
#: Host directories that every program shares (SSH agent and X11 sockets...): no stack may use
#: them or a directory containing them (a directory of its own inside them is fine).
SHARED_DIRS = ("/tmp",)

#: The images a stack builds: <IMAGE_PREFIX>-<name>:latest.
STACK_IMAGES = ("api", "ocr")
#: The service settings a stack other than production may use, as `docker compose config
#: --format json` writes them. Anything else is refused: privileged, cap_add, volumes_from,
#: use_api_socket, pid, ipc, uts, userns_mode, cgroup, labels, env_file, label_file, sysctls,
#: secrets... A setting that a change needs is added here, in the same pull request.
SERVICE_KEYS = frozenset(
    {
        "build",
        "cap_drop",
        "command",
        "container_name",
        "depends_on",
        "devices",
        "entrypoint",
        "environment",
        "healthcheck",
        "image",
        "init",
        "logging",
        "mem_limit",
        "network_mode",
        "networks",
        "pids_limit",
        "ports",
        "profiles",
        "pull_policy",
        "read_only",
        "restart",
        "security_opt",
        "shm_size",
        "stop_grace_period",
        "tmpfs",
        "user",
        "volumes",
        "working_dir",
    }
)
#: The build settings allowed (no ssh, secrets, tags, network, entitlements...).
BUILD_KEYS = frozenset({"context", "dockerfile", "target", "args", "additional_contexts"})
#: The only device a stack may use: the GPU, through CDI.
_GPU_DEVICE = re.compile(r"nvidia\.com/gpu=[A-Za-z0-9_.,:-]+")
_NO_NEW_PRIVILEGES = frozenset({"no-new-privileges", "no-new-privileges:true", "no-new-privileges=true"})
#: Top-level settings allowed besides the x-* extensions (no secrets, configs, models...).
TOP_LEVEL_KEYS = frozenset({"name", "services", "networks", "volumes"})
#: An `include` key of a compose file, in block (YAML) or flow (JSON) style: docker compose
#: config merges what it includes and leaves no trace of it (nor of its env_file).
_INCLUDE = re.compile(r"""(^|[{,])[ \t]*["']?include["']?[ \t]*:""", re.MULTILINE)


class EnvError(ValueError):
    """A .env file that breaks the strict format, or a production that cannot be described."""


def read_env(path: str | os.PathLike[str]) -> dict[str, str]:
    """The KEY=VALUE pairs of a .env file in the strict format (see the module docstring)."""
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise EnvError(f"{path}: {exc.strerror}") from exc
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EnvError(f"{path}: not UTF-8 text") from exc
    if "\r" in text:
        raise EnvError(f"{path}: carriage returns (CRLF line endings?): use LF line endings only")
    values: dict[str, str] = {}
    for number, line in enumerate(text.split("\n"), 1):
        if not line or line.startswith("#"):
            continue
        where = f"{path}, line {number}"
        key, equals, value = line.partition("=")
        if not equals or not _KEY.fullmatch(key):
            raise EnvError(
                f"{where}: expected KEY=VALUE (KEY in capital letters, nothing before it, no spaces "
                f"around '='), a comment starting with '#' in the first column, or a blank line: {line!r}"
            )
        if not _VALUE.fullmatch(value):
            raise EnvError(
                f"{where}: the value of {key} may only contain letters, digits and _ . / : @ % + , - "
                f"(no spaces, quotes, '$', '#', '\\', and no comment after the value): {value!r}"
            )
        if _FORBIDDEN_KEY.match(key):
            raise EnvError(f"{where}: {key} would change what docker compose does: not allowed in .env")
        if key in values:
            raise EnvError(f"{where}: {key} is set twice")
        values[key] = value
    return values


# -- paths ------------------------------------------------------------------


def real(path: str) -> str:
    return os.path.realpath(path)


def contains(parent: str, child: str) -> bool:
    """Whether the real path `child` is `parent` or inside it."""
    return child == parent or child.startswith(parent.rstrip("/") + "/")


def user_home() -> str:
    """This user's home directory, from the password database: $HOME can point elsewhere."""
    return pwd.getpwuid(os.getuid()).pw_dir


def homes() -> set[str]:
    """The real paths of the home directories no stack may use: the user's, and $HOME."""
    found = {real(user_home())}
    if os.environ.get("HOME", "").startswith("/"):
        found.add(real(os.environ["HOME"]))
    return found


def production_checkout(containers: list[JsonObject]) -> Path:
    """Production's checkout: the project directory of production's containers (`docker
    inspect`), else ~/Dev/scanmylib."""
    directories = sorted(
        {
            str(((container.get("Config") or {}).get("Labels") or {}).get(WORKING_DIR_LABEL) or "")
            for container in containers
        }
        - {""}
    )
    if len(directories) > 1:
        raise EnvError(
            f"production's containers come from several checkouts ({', '.join(directories)}): fix production first"
        )
    if directories:
        return Path(real(directories[0]))
    return Path(real(os.path.join(user_home(), DEFAULT_CHECKOUT)))


# -- images -----------------------------------------------------------------


def normalize_image(reference: str) -> str:
    """An image reference as Docker reads it: docker.io/library/NAME:latest for a bare NAME
    (github.com/distribution/reference, ParseNormalizedNamed and TagNameOnly)."""
    name, _, digest = reference.partition("@")
    tag = ""
    if name.rfind(":") > name.rfind("/"):
        name, tag = name[: name.rfind(":")], name[name.rfind(":") + 1 :]
    first, slash, rest = name.partition("/")
    if not slash or (
        not any(character in first for character in ".:") and first != "localhost" and first.lower() == first
    ):
        domain, remainder = "docker.io", name
    else:
        domain, remainder = first, rest
    if domain == "index.docker.io":
        domain = "docker.io"
    if domain == "docker.io" and "/" not in remainder:
        remainder = f"library/{remainder}"
    normalized = f"{domain}/{remainder}"
    if tag or not digest:
        normalized += f":{tag or 'latest'}"
    return f"{normalized}@{digest}" if digest else normalized


def repository(image: str) -> str:
    """The normalized image name, without its tag or digest (registry ports kept)."""
    image = normalize_image(image).split("@", 1)[0]
    return image[: image.rfind(":")] if image.rfind(":") > image.rfind("/") else image


# -- production -------------------------------------------------------------


@dataclass
class Production:
    """What production owns."""

    checkout: Path | None = None
    projects: set[str] = field(default_factory=set)
    repositories: set[str] = field(default_factory=set)  # normalized image names, without their tag
    ports: set[int] = field(default_factory=set)
    container_names: set[str] = field(default_factory=set)
    paths: dict[str, str] = field(default_factory=dict)  # description -> real path
    sandbox: set[str] = field(default_factory=set)  # read-only shareable: the OCR models
    keystore: set[str] = field(default_factory=set)  # read-only shareable: the signing key

    def relations(self, path: str) -> list[str]:
        """How the real path `path` relates to production's paths ("is inside production's
        DATA_DIR (/data/...)"...): empty when it shares nothing with them."""
        relations = []
        for description, other in self.paths.items():
            if path == other:
                relations.append(f"is production's {description} ({other})")
            elif contains(other, path):
                relations.append(f"is inside production's {description} ({other})")
            elif contains(path, other):
                relations.append(f"contains production's {description} ({other})")
        return relations


def production_identity(checkout: Path, containers: list[JsonObject]) -> Production:
    """Production as described by the .env of its checkout, the defaults of .env.example, and
    its containers (`docker inspect`)."""
    env_file = checkout / ".env"
    try:
        env = read_env(env_file) if env_file.exists() else {}
    except EnvError as exc:
        raise EnvError(f"production's .env cannot be read ({exc}): fix it first") from exc
    home, user = user_home(), pwd.getpwuid(os.getuid()).pw_name
    production = Production(checkout=checkout)
    production.projects = {PRODUCTION_PROJECT, env.get("COMPOSE_PROJECT_NAME") or PRODUCTION_PROJECT}
    prefixes = production.projects | {env.get("IMAGE_PREFIX") or PRODUCTION_PROJECT}
    production.repositories = {repository(f"{prefix}-{name}") for prefix in prefixes for name in STACK_IMAGES}
    try:
        production.ports = {int(env.get("API_PORT") or 8765), 8765}
    except ValueError as exc:
        raise EnvError(f"production's .env: API_PORT is not a port number: {env.get('API_PORT')!r}") from exc

    default_data = f"/data/{user}/scanmylib"
    paths = {
        "checkout": str(checkout),
        "default DATA_DIR": default_data,
        "default LIBRARY_DIR": f"{home}/Documents/ScanMyLib",
    }
    data = env.get("DATA_DIR") or default_data
    android = env.get("ANDROID_DIR") or f"{data}/android"
    configured = {
        "DATA_DIR": data,
        "LIBRARY_DIR": env.get("LIBRARY_DIR") or f"{home}/Documents/ScanMyLib",
        "SANDBOX_DIR": env.get("SANDBOX_DIR") or f"{data}/sandbox",
        "ANDROID_DIR": android,
        "signing key directory": env.get("ANDROID_KEYSTORE_DIR") or f"{android}/keystore",
    }
    if env.get("SANDBOX_SETUP_DIR"):
        configured["SANDBOX_SETUP_DIR"] = env["SANDBOX_SETUP_DIR"]
    for key, value in configured.items():
        if not value.startswith("/"):
            raise EnvError(f"production's .env: {key} is not an absolute path: {value!r}")
        paths[key] = value
    production.sandbox = {real(configured["SANDBOX_DIR"]), real(f"{default_data}/sandbox")}
    production.keystore = {real(configured["signing key directory"]), real(f"{default_data}/android/keystore")}

    for container in containers:
        name = str(container.get("Name") or "").lstrip("/")
        production.container_names.add(name)
        labels = (container.get("Config") or {}).get("Labels") or {}
        if labels.get("com.docker.compose.project"):
            production.projects.add(labels["com.docker.compose.project"])
        image = str((container.get("Config") or {}).get("Image") or "")
        if image and not image.startswith("sha256:"):
            production.repositories.add(repository(image))
        for mount in container.get("Mounts") or []:
            if mount.get("Type") == "bind" and mount.get("Source"):
                paths[f"mount {mount.get('Destination')} of {name}"] = mount["Source"]
                if mount.get("Destination") == "/opt/sandbox":
                    production.sandbox.add(real(mount["Source"]))
        bindings = (container.get("HostConfig") or {}).get("PortBindings") or {}
        for host_ports in bindings.values():
            for binding in host_ports or []:
                if str(binding.get("HostPort") or "").isdigit():
                    production.ports.add(int(binding["HostPort"]))
    production.paths = {description: real(path) for description, path in paths.items()}
    return production


# -- isolation ----------------------------------------------------------------


def path_problems(
    what: str,
    path: str,
    production: Production,
    *,
    inside: str | None = None,
    read_only: bool = False,
    shareable: Collection[str] = frozenset(),
    outside_home: bool = True,
) -> list[str]:
    """Why a host path that a stack uses is not its own (an empty list when it is): it must be
    absolute, outside the system directories (and, with `outside_home`, the home directories),
    neither be nor contain /tmp, share nothing with production's paths and, when `inside` is
    given (the stack's DATA_DIR), be inside it. Read-only, it may instead be inside one of the
    `shareable` paths (production's OCR models or signing key)."""
    if not path.startswith("/"):
        return [f"{what}: '{path}' is not an absolute path"]
    resolved = real(path)
    problems = []
    for system in SYSTEM_DIRS:
        if contains(real(system), resolved):
            problems.append(f"{what}: {path} is a system directory ({system})")
            break
    for shared in SHARED_DIRS:
        if contains(resolved, real(shared)):
            problems.append(f"{what}: {path} is or contains {shared}, which every program shares")
    for home in sorted(homes()) if outside_home else ():
        if contains(resolved, home):
            problems.append(f"{what}: {path} contains your home directory ({home})")
        elif contains(home, resolved):
            problems.append(f"{what}: {path} is inside your home directory ({home}), where your secrets are")
    if read_only and any(contains(shared, resolved) for shared in shareable):
        return problems
    if inside is not None and not contains(inside, resolved):
        problems.append(f"{what}: {path} is not inside the stack's DATA_DIR ({inside})")
    problems += [f"{what}: {path} {relation}" for relation in production.relations(resolved)]
    return problems


def _missing(path: str) -> bool:
    """Whether the absolute `path` does not exist, for anyone: a path this user cannot see (in
    /root...) may exist for the Docker daemon."""
    if not path.startswith("/"):
        return False
    try:
        os.lstat(path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def _published(value: object) -> list[int]:
    text = str(value or "")
    if re.fullmatch(r"\d+", text):
        return [int(text)]
    if match := re.fullmatch(r"(\d+)-(\d+)", text):
        return list(range(int(match[1]), int(match[2]) + 1))
    return []


def _settings_problems(name: str, service: JsonObject) -> list[str]:
    return [
        f"service {name}: {key} is not allowed outside production (scripts/lib/stack.py, SERVICE_KEYS)"
        for key in sorted(set(service) - SERVICE_KEYS)
    ]


def _service_problems(
    name: str,
    service: JsonObject,
    *,
    config: JsonObject,
    project: str,
    prefix: str,
    project_dir: str | None,
    data_dir: str | None,
    production: Production,
) -> list[str]:
    what = f"service {name}"
    problems = _settings_problems(name, service)

    image = str(service.get("image") or f"{project}-{name}")
    own = {f"{prefix}-{image_name}:latest" for image_name in STACK_IMAGES}
    if repository(image) in production.repositories:
        problems.append(f"{what}: the image {image} is production's")
    elif image not in own:
        problems.append(f"{what}: the image {image} is not one of the stack's own ({', '.join(sorted(own))})")
    container_name = service.get("container_name")
    if container_name and (
        container_name in production.container_names or not container_name.startswith(f"{project}-")
    ):
        problems.append(f"{what}: container_name {container_name} is not in the project {project}")
    # The stack's own networks only: none, another of its services', or those of `networks`
    # (checked below), never the host's, a container's or another project's network by name.
    network_mode = str(service.get("network_mode") or "none")
    other_service = network_mode.removeprefix("service:") if network_mode.startswith("service:") else None
    if network_mode != "none" and other_service not in set(config.get("services") or {}) - {name}:
        problems.append(
            f"{what}: network_mode {network_mode} is not allowed (only none, or service:<another "
            "service of the stack>; other networks go in networks)"
        )
    for network in service.get("networks") or {}:
        if network not in (config.get("networks") or {}):
            problems.append(f"{what}: the network {network} is not one of the stack's networks")
    for option in service.get("security_opt") or []:
        if option not in _NO_NEW_PRIVILEGES:
            problems.append(f"{what}: security_opt {option} is not allowed (only no-new-privileges)")
    for device in service.get("devices") or []:
        source = str(device.get("source") or "") if isinstance(device, dict) else str(device)
        target = str(device.get("target") or "") if isinstance(device, dict) else source
        if not _GPU_DEVICE.fullmatch(source) or target != source:
            problems.append(f"{what}: device {source} is not allowed (only the GPU through CDI, nvidia.com/gpu=...)")

    build = service.get("build")
    if build is not None:
        build = build if isinstance(build, dict) else {"context": build}
        problems += [
            f"{what}: build setting {key} is not allowed (scripts/lib/stack.py, BUILD_KEYS)"
            for key in sorted(set(build) - BUILD_KEYS)
        ]
        contexts = {"context": build.get("context")}
        contexts.update(
            {f"additional context {key}": value for key, value in (build.get("additional_contexts") or {}).items()}
        )
        for description, context in contexts.items():
            context = str(context or "")
            if not (project_dir and context.startswith("/") and contains(real(project_dir), real(context))):
                problems.append(
                    f"{what}: build {description} {context or '(none)'} is not inside the "
                    f"project directory ({project_dir})"
                )

    for port in service.get("ports") or []:
        for number in _published(port.get("published")):
            if number in production.ports:
                problems.append(f"{what}: publishes port {number}, production's")
    for volume in service.get("volumes") or []:
        kind = volume.get("type")
        source = str(volume.get("source") or "")
        if kind == "bind":
            if not (volume.get("bind") or {}).get("create_host_path") and _missing(source):
                continue  # docker refuses to start the container: never mounted
            problems += path_problems(
                f"{what}: bind mount {source} -> {volume.get('target')}",
                source,
                production,
                inside=data_dir,
                read_only=bool(volume.get("read_only")),
                shareable=production.sandbox,
            )
        elif kind not in ("volume", "tmpfs"):
            problems.append(f"{what}: {kind} mount {source} is not allowed")
    return problems


def isolation_problems(
    env: dict[str, str],
    config: JsonObject,
    raw: JsonObject,
    production: Production,
    project_dir: str | None = None,
    compose_file: str | None = None,
) -> list[str]:
    """What the stack (its .env, and what docker compose resolves from `compose_file` with the
    project directory `project_dir`: `config`, and `raw` without interpolation) shares with
    production or uses outside its own DATA_DIR."""
    problems: list[str] = []
    project = str(config.get("name") or "")
    if not project:
        problems.append("docker compose resolves no project name")
    elif project in production.projects:
        problems.append(f"the project is production's: {project}")
    if env.get("COMPOSE_PROJECT_NAME") != project:
        problems.append(
            f"docker compose resolves the project {project!r}, .env says {env.get('COMPOSE_PROJECT_NAME')!r}"
        )
    prefix = env.get("IMAGE_PREFIX") or project
    if not _IMAGE_PREFIX.fullmatch(prefix):
        problems.append(f"IMAGE_PREFIX {prefix!r} may only contain lowercase letters, digits and '-'")

    # The stack's own directory: every other host path it uses must be inside it.
    data_dir = None
    if not env.get("DATA_DIR"):
        problems.append("no DATA_DIR in .env")
    else:
        own = path_problems("DATA_DIR in .env", env["DATA_DIR"], production)
        problems += own
        if not own:
            data_dir = real(env["DATA_DIR"])

    for key in sorted(set(config) - TOP_LEVEL_KEYS):
        if not key.startswith("x-"):
            problems.append(f"{key} (top level) is not allowed outside production (scripts/lib/stack.py)")
    if compose_file and _INCLUDE.search(Path(compose_file).read_text(encoding="utf-8", errors="replace")):
        problems.append(f"{compose_file}: include is not allowed outside production (its env_file reads host files)")
    for name, service in (config.get("services") or {}).items():
        problems += _service_problems(
            name,
            service or {},
            config=config,
            project=project,
            prefix=prefix,
            project_dir=project_dir,
            data_dir=data_dir,
            production=production,
        )
    # Interpolated, env_file and label_file are merged into environment and labels, and gone.
    if not (raw.get("services") or {}):
        problems.append("no configuration without interpolation (docker compose config --no-interpolate)")
    for name, service in (raw.get("services") or {}).items():
        problems += _settings_problems(name, service or {})
    for kind in ("networks", "volumes"):
        for key, item in (config.get(kind) or {}).items():
            item = item or {}
            name = str(item.get("name") or "")
            if item.get("external") or not name.startswith(f"{project}_"):
                problems.append(f"{kind[:-1]} {key} ({name or 'external'}) is not the stack's own")
            if kind == "volumes" and (item.get("driver_opts") or item.get("driver") not in (None, "local")):
                problems.append(f"volume {key}: driver and driver_opts are not allowed (they can mount host paths)")
            if kind == "networks" and (item.get("driver_opts") or item.get("driver") not in (None, "bridge")):
                problems.append(
                    f"network {key}: driver and driver_opts are not allowed (macvlan or ipvlan reach the LAN directly)"
                )

    # The paths the scripts use themselves (state, backups, logs, Android toolchain, APK).
    for key in ("LIBRARY_DIR", "ANDROID_DIR", "SANDBOX_SETUP_DIR"):
        if env.get(key):
            problems += path_problems(f"{key} in .env", env[key], production, inside=data_dir)
    if env.get("SANDBOX_DIR"):
        problems += path_problems(
            "SANDBOX_DIR in .env",
            env["SANDBOX_DIR"],
            production,
            inside=data_dir,
            read_only=True,
            shareable=production.sandbox,
        )
    if env.get("ANDROID_KEYSTORE_DIR"):
        problems += path_problems(
            "ANDROID_KEYSTORE_DIR in .env",
            env["ANDROID_KEYSTORE_DIR"],
            production,
            inside=data_dir,
            read_only=True,
            shareable=production.keystore,
        )
    if env.get("APP_VARIANT", "dev") != "dev":
        problems.append(f"APP_VARIANT={env['APP_VARIANT']}: only production builds the release app")
    if env.get("OCR_SERVICE", "ocr-fake") not in ("ocr", "ocr-fake"):
        problems.append(f"OCR_SERVICE={env['OCR_SERVICE']}: expected ocr or ocr-fake")
    return list(dict.fromkeys(problems))


# -- docker compose command lines ----------------------------------------------

#: The docker compose commands that scripts/dev.sh passes on: they only work on the stack's own
#: containers, images, networks and volumes. Refused: cp and export (host paths), commit (it
#: could tag an image with production's name), push, publish and pull (registries), watch, bridge,
#: scale (it starts services by SERVICE=NUM, both OCR services included).
COMPOSE_COMMANDS = frozenset(
    {
        "attach",
        "build",
        "config",
        "create",
        "down",
        "events",
        "exec",
        "images",
        "kill",
        "logs",
        "ls",
        "pause",
        "port",
        "ps",
        "restart",
        "rm",
        "run",
        "start",
        "stats",
        "stop",
        "top",
        "unpause",
        "up",
        "version",
        "volumes",
        "wait",
    }
)
#: What scripts/prod.sh passes on: no build nor one-off container (production changes through
#: scripts/deploy.sh).
PRODUCTION_COMPOSE_COMMANDS = COMPOSE_COMMANDS - {"build", "create", "run"}
#: The options of the commands that could give a container (or the host) more than compose.yaml
#: does, as (flags, options taking a value); any other option is refused, e.g. run -v/--volume,
#: -p/--publish, --cap-add, --env-from-file, -l/--label, --name; exec --privileged; build --ssh,
#: --push; config -o/--output; up --watch. Options of run and exec come before the service (what
#: follows it is the command run in the container); those of the other commands anywhere before
#: "--", service names included.
COMMAND_OPTIONS = {
    "run": (
        {
            "--build",
            "-d",
            "--detach",
            "--dry-run",
            "-i",
            "--interactive",
            "--no-deps",
            "-q",
            "--quiet",
            "--quiet-build",
            "--quiet-pull",
            "--remove-orphans",
            "--rm",
            "-P",
            "--service-ports",
            "-T",
            "--no-TTY",
            "--use-aliases",
        },
        {"--cap-drop", "--entrypoint", "-e", "--env", "--pull", "-u", "--user", "-w", "--workdir"},
    ),
    "exec": (
        {"-d", "--detach", "--dry-run", "-T", "--no-tty"},
        {"-e", "--env", "--index", "-u", "--user", "-w", "--workdir"},
    ),
    "build": (
        {"--check", "--dry-run", "--no-cache", "--print", "--pull", "-q", "--quiet", "--with-dependencies"},
        {"--build-arg", "--builder", "-m", "--memory", "--provenance", "--sbom"},
    ),
    "config": (
        {
            "--dry-run",
            "--environment",
            "--images",
            "--models",
            "--networks",
            "--no-consistency",
            "--no-env-resolution",
            "--no-interpolate",
            "--no-normalize",
            "--no-path-resolution",
            "--profiles",
            "-q",
            "--quiet",
            "--services",
            "--variables",
            "--volumes",
        },
        {"--format", "--hash"},
    ),
    "up": (
        {
            "--abort-on-container-exit",
            "--abort-on-container-failure",
            "--always-recreate-deps",
            "--attach-dependencies",
            "--build",
            "-d",
            "--detach",
            "--dry-run",
            "--force-recreate",
            "--menu",
            "--no-build",
            "--no-color",
            "--no-deps",
            "--no-log-prefix",
            "--no-recreate",
            "--no-start",
            "--quiet-build",
            "--quiet-pull",
            "--remove-orphans",
            "-V",
            "--renew-anon-volumes",
            "--timestamps",
            "--wait",
            "-y",
            "--yes",
        },
        {"--attach", "--exit-code-from", "--no-attach", "--pull", "-t", "--timeout", "--wait-timeout"},
    ),
    "create": (
        {
            "--build",
            "--dry-run",
            "--force-recreate",
            "--no-build",
            "--no-recreate",
            "--quiet-pull",
            "--remove-orphans",
            "-y",
            "--yes",
        },
        {"--pull"},
    ),
    "start": ({"--dry-run"}, set()),
    "restart": ({"--dry-run", "--no-deps"}, {"-t", "--timeout"}),
}
#: Commands whose options end at the service: what follows it is the command run in the container.
_IN_CONTAINER = frozenset({"run", "exec"})
#: Commands that start services: with no service named, docker compose starts them all.
STARTING_COMMANDS = frozenset({"up", "create", "start", "restart"})


def compose_command_problems(argv: list[str], *, production: bool = False) -> list[str]:
    """Why scripts/dev.sh (or, with `production`, scripts/prod.sh) refuses `docker compose ARGV`."""
    if not argv or not re.fullmatch(r"[a-z][a-z-]*", argv[0]):
        return ["expected a docker compose command first (no global option such as -p, -f or --env-file)"]
    command, arguments = argv[0], argv[1:]
    if command not in (PRODUCTION_COMPOSE_COMMANDS if production else COMPOSE_COMMANDS):
        reason = (
            "production changes through scripts/deploy.sh"
            if production and command in COMPOSE_COMMANDS
            else "it could reach outside the stack"
        )
        return [f"docker compose {command} is not allowed here: {reason}"]
    problems = []
    if production and any(argument == "--build" or argument.startswith("--build=") for argument in arguments):
        problems.append(f"{command} --build: production's images are built by scripts/deploy.sh only")
    if command not in COMMAND_OPTIONS:
        return problems
    flags, options = COMMAND_OPTIONS[command]
    services: list[str] = []
    remaining = iter(arguments)
    for argument in remaining:
        if argument == "--" or argument == "-" or not argument.startswith("-"):
            if command in _IN_CONTAINER:
                break  # the service: what follows is the command run in the container
            services += list(remaining) if argument == "--" else [argument]
            continue
        if argument.startswith("--"):
            name, equals, _ = argument.partition("=")
            if name in options:
                if not equals:
                    next(remaining, None)
            elif name not in flags:
                problems.append(f"{command} {name} is not allowed here (scripts/lib/stack.py, COMMAND_OPTIONS)")
            continue
        for index, letter in enumerate(argument[1:], 1):  # -dT, -e VALUE, -eVALUE
            short = f"-{letter}"
            if short in flags:
                continue
            if short in options:
                if index == len(argument) - 1:
                    next(remaining, None)
            else:
                problems.append(f"{command} {short} is not allowed here (scripts/lib/stack.py, COMMAND_OPTIONS)")
            break

    # ocr and ocr-fake serve the same socket: never both, and the fake OCR never in production.
    if command in STARTING_COMMANDS:
        if {"ocr", "ocr-fake"} <= set(services):
            problems.append(f"{command} ocr ocr-fake: both OCR services serve the same socket, never start both")
        if production and "ocr-fake" in services:
            problems.append(f"{command} ocr-fake: the fake OCR never runs in production")
        if not production and not services:
            problems.append(
                f"{command} without service names would start both OCR services, which serve the same "
                f"socket: name them (e.g. {command} api ocr-fake, or api ocr)"
            )
    return problems


# -- command line -------------------------------------------------------------


def _read_containers() -> list[JsonObject]:
    text = sys.stdin.read()
    return json.loads(text) if text.strip() else []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    env_command = commands.add_parser("env", help="check a .env and print its KEY=VALUE lines")
    env_command.add_argument("file")
    commands.add_parser("production-checkout", help="production's checkout (containers on stdin)")
    check = commands.add_parser("check-isolation", help="what a stack shares with production")
    check.add_argument("--env", required=True, help="the stack's .env")
    check.add_argument("--project-dir", required=True, help="the project directory (build contexts)")
    check.add_argument("--compose-file", required=True, help="the compose file docker compose read")
    paths = commands.add_parser("check-paths", help="host paths that are production's (containers on stdin)")
    paths.add_argument("--runner-temp", help="GitHub Actions' RUNNER_TEMP: paths inside it may be in your home")
    paths.add_argument("paths", nargs="+", metavar="NAME=PATH")
    compose = commands.add_parser("check-compose-command", help="a docker compose command of dev.sh or prod.sh")
    compose.add_argument("--production", action="store_true", help="the rules of scripts/prod.sh")
    compose.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    try:
        if args.command == "env":
            for key, value in read_env(args.file).items():
                print(f"{key}={value}")
            return 0
        if args.command == "production-checkout":
            print(production_checkout(_read_containers()))
            return 0
        if args.command == "check-compose-command":
            command = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
            problems = compose_command_problems(command, production=args.production)
        elif args.command == "check-paths":
            containers = _read_containers()
            production = production_identity(production_checkout(containers), containers)
            problems, runner_temp = [], None
            if args.runner_temp:
                # GitHub's runner keeps its temporary directory in its home directory.
                problems = path_problems("RUNNER_TEMP", args.runner_temp, production, outside_home=False)
                runner_temp = real(args.runner_temp) if args.runner_temp.startswith("/") else None
                problems += [
                    f"RUNNER_TEMP: {args.runner_temp} is or contains your home directory ({home})"
                    for home in sorted(homes())
                    if runner_temp and contains(runner_temp, home)
                ]
            for item in args.paths:
                name, _, path = item.partition("=")
                in_runner_temp = runner_temp is not None and path.startswith("/") and contains(runner_temp, real(path))
                problems += path_problems(name, path, production, outside_home=not in_runner_temp)
        else:
            env = read_env(args.env)
            state = json.load(sys.stdin)
            containers = state.get("containers") or []
            production = production_identity(production_checkout(containers), containers)
            problems = isolation_problems(
                env, state.get("config") or {}, state.get("raw") or {}, production, args.project_dir, args.compose_file
            )
    except EnvError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
