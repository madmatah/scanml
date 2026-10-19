"""scripts/lib/stack.py: the strict .env format, production's checkout and the isolation of a stack.

Standard library only: python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import functools
import io
import json
import os
import re
import sys
import tempfile
import types
import unittest
from collections.abc import Mapping, Sequence
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import stack

DEVELOPMENT_STACK_ENV = """\
# A development stack.
COMPOSE_PROJECT_NAME=scanmylib-dev
IMAGE_PREFIX=scanmylib-dev

DATA_DIR={development_data_dir}
SANDBOX_DIR={production_data_dir}/sandbox
ANDROID_DIR={development_data_dir}/android
ANDROID_KEYSTORE_DIR={production_data_dir}/android/keystore
LIBRARY_DIR={development_data_dir}/library
API_PORT=8770
PUBLIC_URL=http://192.168.1.10:8770
OCR_SERVICE=ocr-fake
APP_VARIANT=dev
"""


@dataclass(frozen=True)
class Layout:
    base: Path
    production_data_dir: Path
    development_data_dir: Path
    home: Path
    primary: Path
    library: Path
    worktree: Path
    env: Mapping[str, str]


def make_directory(test: unittest.TestCase) -> Path:
    return Path(os.path.realpath(test.enterContext(tempfile.TemporaryDirectory(prefix="scanmylib-stack-"))))


def write_env(path: Path, text: str | bytes) -> Path:
    path.write_bytes(text.encode() if isinstance(text, str) else text)
    return path


def fake_home(test: unittest.TestCase, home: Path) -> None:
    test.enterContext(mock.patch.dict(os.environ, {"HOME": str(home)}))
    test.enterContext(mock.patch.object(stack, "user_home", return_value=str(home)))


def make_home(test: unittest.TestCase) -> Path:
    home = make_directory(test)
    fake_home(test, home)
    return home


def build_container(working_dir: str) -> stack.JsonObject:
    return {"Name": "/scanmylib-api-1", "Config": {"Labels": {stack.WORKING_DIR_LABEL: working_dir}}}


def make_layout(test: unittest.TestCase) -> Layout:
    base = make_directory(test)
    production_data_dir, development_data_dir = base / "prod", base / "prod-dev"
    home = base / "home"
    primary = home / "Dev" / "scanmylib"
    library = home / "Documents" / "ScanMyLib"
    primary.mkdir(parents=True)
    fake_home(test, home)
    (primary / ".env").write_text(
        f"COMPOSE_PROJECT_NAME=scanmylib\nIMAGE_PREFIX=scanmylib\nDATA_DIR={production_data_dir}\n"
        f"SANDBOX_DIR={production_data_dir}/sandbox\nANDROID_DIR={production_data_dir}/android\n"
        f"LIBRARY_DIR={library}\nAPI_PORT=8765\nSANDBOX_SETUP_DIR={production_data_dir}/sandbox\n"
    )
    env = dict(
        line.split("=", 1)
        for line in DEVELOPMENT_STACK_ENV.format(
            development_data_dir=development_data_dir, production_data_dir=production_data_dir
        ).splitlines()
        if line and not line.startswith("#")
    )
    return Layout(base, production_data_dir, development_data_dir, home, primary, library, base / "worktree", env)


def build_resolved_compose_config(layout: Layout, **changes: object) -> stack.JsonObject:
    development_data_dir, production_data_dir = layout.development_data_dir, layout.production_data_dir
    worktree = layout.worktree
    created = {"create_host_path": True}
    config: stack.JsonObject = {
        "name": "scanmylib-dev",
        "networks": {"default": {"name": "scanmylib-dev_default", "ipam": {}}},
        "x-ocr-env": {"HOME": "/tmp/home"},
        "services": {
            "api": {
                "build": {
                    "context": f"{worktree}/server",
                    "dockerfile": "Dockerfile",
                    "target": "runtime",
                    "args": {"UID": "1000"},
                    "additional_contexts": {"project": str(worktree)},
                },
                "image": "scanmylib-dev-api:latest",
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "read_only": True,
                "ports": [{"target": 8765, "published": "8770"}],
                "tmpfs": ["/tmp:size=512m,mode=1777"],
                "networks": {"default": None},
                "volumes": [
                    {
                        "type": "bind",
                        "source": f"{development_data_dir}/library",
                        "target": "/library",
                        "bind": created,
                    },
                    {"type": "bind", "source": f"{development_data_dir}/state", "target": "/state", "bind": created},
                    {
                        "type": "bind",
                        "source": f"{development_data_dir}/run",
                        "target": "/run/scanmylib",
                        "bind": created,
                    },
                    {
                        "type": "bind",
                        "source": f"{development_data_dir}/app",
                        "target": "/app-dist",
                        "read_only": True,
                        "bind": created,
                    },
                ],
            },
            "ocr": {
                "build": {"context": f"{worktree}/ocr", "dockerfile": "Dockerfile"},
                "image": "scanmylib-dev-ocr:latest",
                "network_mode": "none",
                "devices": [{"source": "nvidia.com/gpu=all", "target": "nvidia.com/gpu=all", "permissions": "rwm"}],
                "volumes": [
                    {
                        "type": "bind",
                        "source": f"{production_data_dir}/sandbox",
                        "target": "/opt/sandbox",
                        "read_only": True,
                        "bind": created,
                    },
                    {
                        "type": "bind",
                        "source": f"{development_data_dir}/run",
                        "target": "/run/scanmylib",
                        "bind": created,
                    },
                    {
                        "type": "bind",
                        "source": f"{development_data_dir}/ocr-cache",
                        "target": "/var/cache/ocr",
                        "bind": created,
                    },
                ],
            },
            "ocr-fake": {
                "image": "scanmylib-dev-api:latest",
                "pull_policy": "never",
                "profiles": ["fake-ocr"],
                "network_mode": "none",
            },
            "ocr-setup": {
                "build": {"context": f"{worktree}/ocr", "dockerfile": "Dockerfile"},
                "image": "scanmylib-dev-ocr:latest",
                "volumes": [
                    {
                        "type": "bind",
                        "source": "/nonexistent/SANDBOX_SETUP_DIR",
                        "target": "/opt/sandbox",
                        "bind": {},
                    }
                ],
            },
        },
    }
    config.update(changes)
    return config


def build_resolved_compose_config_with_settings(
    layout: Layout, service: str = "api", **settings: object
) -> stack.JsonObject:
    config = build_resolved_compose_config(layout)
    config["services"][service].update(settings)
    return config


def build_resolved_compose_config_with_bind_mount(
    layout: Layout, source: str, read_only: bool = False, service: str = "api", create: bool = True
) -> stack.JsonObject:
    config = build_resolved_compose_config(layout)
    config["services"][service]["volumes"].append(
        {
            "type": "bind",
            "source": source,
            "target": "/x",
            "read_only": read_only,
            "bind": {"create_host_path": True} if create else {},
        }
    )
    return config


def find_problems(
    layout: Layout,
    config: stack.JsonObject | None = None,
    env: Mapping[str, str] | None = None,
    containers: Sequence[stack.JsonObject] = (),
    raw: stack.JsonObject | None = None,
    compose_file: str | None = None,
) -> list[str]:
    checkout = stack.production_checkout(list(containers))
    production = stack.production_identity(checkout, list(containers))
    config = config or build_resolved_compose_config(layout)
    return stack.isolation_problems(
        dict(env or layout.env), config, raw or config, production, str(layout.worktree), compose_file
    )


def mentions(problems: list[str], text: str) -> bool:
    return any(text in problem for problem in problems)


def run_check_paths(*arguments: str) -> tuple[int, str]:
    errors = io.StringIO()
    with mock.patch("sys.stdin", io.StringIO("[]")), redirect_stderr(errors):
        return stack.main(["check-paths", *arguments]), errors.getvalue()


class TheReadEnvFunctionWhenTheFileKeepsToTheStrictFormat(unittest.TestCase):
    def setUp(self) -> None:
        path = write_env(
            make_directory(self) / ".env",
            "# comment\n\nA=1\nPUBLIC_URL=http://192.168.1.10:8765\nEMPTY=\nLAST=a/b_c.d@e%f+g,h-i",
        )
        self.values = stack.read_env(path)

    def test_should_read_its_key_value_lines_and_skip_its_comments_and_blank_lines(self) -> None:
        self.assertEqual(
            self.values,
            {"A": "1", "PUBLIC_URL": "http://192.168.1.10:8765", "EMPTY": "", "LAST": "a/b_c.d@e%f+g,h-i"},
        )


class TheReadEnvFunctionWhenALineWouldReadDifferentlyInDockerCompose(unittest.TestCase):
    #: Each line makes docker compose resolve COMPOSE_PROJECT_NAME=scanmylib, while a naive parser
    #: (sed 's/^KEY=//') reads something else; and the reason of its refusal.
    lines: ClassVar[Mapping[str, tuple[str, str]]] = types.MappingProxyType(
        {
            "a comment after the value": ("COMPOSE_PROJECT_NAME=scanmylib # dev\n", "may only contain"),
            "a space after the value": ("COMPOSE_PROJECT_NAME=scanmylib \n", "may only contain"),
            "an export": (
                "COMPOSE_PROJECT_NAME=scanmylib-dev\nexport COMPOSE_PROJECT_NAME=scanmylib\n",
                "expected KEY=VALUE",
            ),
            "an indented key": (
                "COMPOSE_PROJECT_NAME=scanmylib-dev\n  COMPOSE_PROJECT_NAME=scanmylib\n",
                "expected KEY=VALUE",
            ),
            "a colon": ("COMPOSE_PROJECT_NAME=scanmylib-dev\nCOMPOSE_PROJECT_NAME: scanmylib\n", "expected KEY=VALUE"),
            "spaces around the equals sign": (
                "COMPOSE_PROJECT_NAME=scanmylib-dev\nCOMPOSE_PROJECT_NAME = scanmylib\n",
                "expected KEY=VALUE",
            ),
            "a braced variable": ("X=scanmylib\nCOMPOSE_PROJECT_NAME=${X}\n", "may only contain"),
            "a variable": ("X=scanmylib\nCOMPOSE_PROJECT_NAME=$X\n", "may only contain"),
            "a carriage return": ("COMPOSE_PROJECT_NAME=scanmylib\r\n", "carriage returns"),
            "a quoted value and a comment": ('COMPOSE_PROJECT_NAME="scanmylib" # x\n', "may only contain"),
            "a single-quoted value": ("COMPOSE_PROJECT_NAME='scanmylib'\n", "may only contain"),
            "a line continued with a backslash": ("COMPOSE_PROJECT_NAME=scanmyli\\\nb\n", "may only contain"),
            "a key set twice": ("COMPOSE_PROJECT_NAME=scanmylib-dev\nCOMPOSE_PROJECT_NAME=scanmylib\n", "is set twice"),
            "a key indented with a tab": ("\tCOMPOSE_PROJECT_NAME=scanmylib\n", "expected KEY=VALUE"),
            "an indented comment": (" # an indented comment\n", "expected KEY=VALUE"),
            "a lowercase key": ("compose_project_name=scanmylib\n", "expected KEY=VALUE"),
            "a key without a value": ("COMPOSE_PROJECT_NAME\n", "expected KEY=VALUE"),
        }
    )

    def setUp(self) -> None:
        directory = make_directory(self)
        self.reading_acts = {
            row: functools.partial(stack.read_env, write_env(directory / f"{index}.env", text))
            for index, (row, (text, _)) in enumerate(self.lines.items())
        }

    def test_should_refuse_it_saying_why_so_that_the_scripts_never_read_another_value_than_docker_compose(
        self,
    ) -> None:
        for row, (_, reason) in self.lines.items():
            with self.subTest(row):
                self.assertRaisesRegex(stack.EnvError, re.escape(reason), self.reading_acts[row])


class TheReadEnvFunctionWhenAKeyChangesWhatDockerComposeDoes(unittest.TestCase):
    keys: ClassVar[tuple[str, ...]] = (
        "COMPOSE_FILE",
        "COMPOSE_PROFILES",
        "COMPOSE_ENV_FILES",
        "COMPOSE_PATH_SEPARATOR",
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "BUILDKIT_PROGRESS",
    )

    def setUp(self) -> None:
        directory = make_directory(self)
        self.reading_acts = {
            key: functools.partial(stack.read_env, write_env(directory / f"{key}.env", f"{key}=x\n"))
            for key in self.keys
        }

    def test_should_refuse_it_naming_it(self) -> None:
        for key in self.keys:
            with self.subTest(key):
                self.assertRaisesRegex(
                    stack.EnvError, f"{key} would change what docker compose does", self.reading_acts[key]
                )


class TheReadEnvFunctionWhenALineBreaksTheFormat(unittest.TestCase):
    def setUp(self) -> None:
        path = write_env(make_directory(self) / ".env", "A=1\n# ok\nB=two words\n")
        self.read = functools.partial(stack.read_env, path)

    def test_should_refuse_it_naming_the_line(self) -> None:
        self.assertRaisesRegex(stack.EnvError, "line 3", self.read)


class TheReadEnvFunctionWhenTheFileIsNotUtf8(unittest.TestCase):
    def setUp(self) -> None:
        path = write_env(make_directory(self) / ".env", b"A=\xff\n")
        self.read = functools.partial(stack.read_env, path)

    def test_should_refuse_it(self) -> None:
        self.assertRaisesRegex(stack.EnvError, "not UTF-8 text", self.read)


class TheReadEnvFunctionWhenTheFileIsMissing(unittest.TestCase):
    def setUp(self) -> None:
        self.missing_path = make_directory(self) / "missing"
        self.read = functools.partial(stack.read_env, self.missing_path)

    def test_should_refuse_it_naming_it(self) -> None:
        self.assertRaisesRegex(stack.EnvError, re.escape(f"{self.missing_path}: "), self.read)


class TheNormalizeImageFunction(unittest.TestCase):
    references: ClassVar[Mapping[str, str]] = types.MappingProxyType(
        {
            "scanmylib-api": "docker.io/library/scanmylib-api:latest",
            "scanmylib-api:latest": "docker.io/library/scanmylib-api:latest",
            "docker.io/scanmylib-api": "docker.io/library/scanmylib-api:latest",
            "docker.io/library/scanmylib-api:deployed": "docker.io/library/scanmylib-api:deployed",
            "index.docker.io/library/scanmylib-api": "docker.io/library/scanmylib-api:latest",
            "someone/scanmylib-api": "docker.io/someone/scanmylib-api:latest",
            "localhost/scanmylib-api": "localhost/scanmylib-api:latest",
            "registry:5000/scanmylib-api": "registry:5000/scanmylib-api:latest",
            "x/y:1@sha256:abc": "docker.io/x/y:1@sha256:abc",
            "x@sha256:abc": "docker.io/library/x@sha256:abc",
        }
    )

    def setUp(self) -> None:
        self.images = {reference: stack.normalize_image(reference) for reference in self.references}

    def test_should_read_each_reference_as_docker_does(self) -> None:
        for reference, image in self.references.items():
            with self.subTest(reference):
                self.assertEqual(self.images[reference], image)


class TheRepositoryFunction(unittest.TestCase):
    images: ClassVar[Mapping[str, str]] = types.MappingProxyType(
        {
            "scanmylib-api:latest": "docker.io/library/scanmylib-api",
            "index.docker.io/library/scanmylib-api": "docker.io/library/scanmylib-api",
            "registry:5000/scanmylib-api": "registry:5000/scanmylib-api",
            "x/y:1@sha256:abc": "docker.io/x/y",
        }
    )

    def setUp(self) -> None:
        self.repositories = {image: stack.repository(image) for image in self.images}

    def test_should_be_the_name_docker_reads_without_its_tag_or_digest(self) -> None:
        for image, repository in self.images.items():
            with self.subTest(image):
                self.assertEqual(self.repositories[image], repository)


class TheProductionCheckoutFunctionWhenProductionHasContainers(unittest.TestCase):
    def setUp(self) -> None:
        self.project_directory = make_home(self) / "elsewhere"
        containers = [build_container(str(self.project_directory)), build_container(str(self.project_directory))]
        self.checkout = stack.production_checkout(containers)

    def test_should_be_the_project_directory_of_its_containers(self) -> None:
        self.assertEqual(self.checkout, self.project_directory)


class TheProductionCheckoutFunctionWhenProductionHasNoContainer(unittest.TestCase):
    def setUp(self) -> None:
        self.home = make_home(self)
        self.checkout = stack.production_checkout([])

    def test_should_be_dev_scanmylib_in_the_home_directory(self) -> None:
        self.assertEqual(self.checkout, self.home / "Dev" / "scanmylib")


class TheProductionCheckoutFunctionWhenHomePointsElsewhere(unittest.TestCase):
    def setUp(self) -> None:
        self.home = make_home(self)
        self.enterContext(mock.patch.dict(os.environ, {"HOME": "/elsewhere"}))
        self.checkout = stack.production_checkout([])

    def test_should_take_the_home_directory_from_the_password_database(self) -> None:
        self.assertEqual(self.checkout, self.home / "Dev" / "scanmylib")


class TheHomesFunctionWhenHomePointsElsewhere(unittest.TestCase):
    def setUp(self) -> None:
        self.home = make_home(self)
        self.enterContext(mock.patch.dict(os.environ, {"HOME": "/elsewhere"}))
        self.homes = stack.homes()

    def test_should_hold_the_home_directory_of_the_password_database_and_home_so_that_no_stack_uses_either(
        self,
    ) -> None:
        self.assertEqual(self.homes, {str(self.home), "/elsewhere"})


class TheProductionCheckoutFunctionWhenProductionsContainersComeFromSeveralCheckouts(unittest.TestCase):
    def setUp(self) -> None:
        make_home(self)
        containers = [build_container("/a"), build_container("/b")]
        self.find_checkout = functools.partial(stack.production_checkout, containers)

    def test_should_refuse_since_production_is_to_be_fixed_first(self) -> None:
        self.assertRaisesRegex(stack.EnvError, "several checkouts", self.find_checkout)


class TheMainFunctionWhenAskedForProductionsCheckout(unittest.TestCase):
    def setUp(self) -> None:
        self.home = make_home(self)
        containers = json.dumps([build_container(f"{self.home}/prod")])
        output = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(containers)), redirect_stdout(output):
            self.exit_code = stack.main(["production-checkout"])
        self.printed = output.getvalue()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.exit_code, 0)

    def test_should_print_the_project_directory_of_the_containers_it_reads(self) -> None:
        self.assertEqual(self.printed.strip(), f"{self.home}/prod")


class TheIsolationProblemsFunctionWhenTheStackIsTheDevelopmentOne(unittest.TestCase):
    def setUp(self) -> None:
        self.problems = find_problems(make_layout(self))

    def test_should_find_none(self) -> None:
        self.assertEqual(self.problems, [])


class TheIsolationProblemsFunctionWhenTheStackTakesWhatProductionOwns(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        configs = {
            "production's project": build_resolved_compose_config(layout, name="scanmylib"),
            "an image of production's": build_resolved_compose_config_with_settings(layout, image="scanmylib-api:dev"),
            "a port range that holds production's port": build_resolved_compose_config_with_settings(
                layout, ports=[{"target": 8765, "published": "8760-8770"}]
            ),
        }
        self.expected_problems = {
            "production's project": "the project is production's",
            "an image of production's": "the image scanmylib-api:dev is production's",
            "a port range that holds production's port": "publishes port 8765",
        }
        self.problems = {row: find_problems(layout, config=config) for row, config in configs.items()}

    def test_should_refuse_it(self) -> None:
        for row, expected in self.expected_problems.items():
            with self.subTest(row):
                self.assertTrue(mentions(self.problems[row], expected), self.problems[row])


class TheIsolationProblemsFunctionWhenAnImageOfProductionsIsWrittenInAnotherForm(unittest.TestCase):
    images: ClassVar[tuple[str, ...]] = (
        "docker.io/library/scanmylib-api:latest",
        "docker.io/scanmylib-api",
        "index.docker.io/library/scanmylib-api:latest",
    )

    def setUp(self) -> None:
        layout = make_layout(self)
        self.problems = {
            image: find_problems(layout, config=build_resolved_compose_config_with_settings(layout, image=image))
            for image in self.images
        }

    def test_should_refuse_it_since_docker_reads_it_as_production_s(self) -> None:
        for image in self.images:
            with self.subTest(image):
                self.assertTrue(
                    mentions(self.problems[image], f"the image {image} is production's"), self.problems[image]
                )


class TheIsolationProblemsFunctionWhenAnImageIsNotOneOfTheStacksOwn(unittest.TestCase):
    images: ClassVar[tuple[str, ...]] = (
        "scanmylib-dev-api:dev",
        "scanmylib-dev-other:latest",
        "docker.io/library/scanmylib-dev-api:latest",
        "busybox:latest",
    )

    def setUp(self) -> None:
        layout = make_layout(self)
        self.problems = {
            image: find_problems(layout, config=build_resolved_compose_config_with_settings(layout, image=image))
            for image in self.images
        }

    def test_should_refuse_it(self) -> None:
        for image in self.images:
            with self.subTest(image):
                self.assertTrue(mentions(self.problems[image], "is not one of the stack's own"), self.problems[image])


class TheIsolationProblemsFunctionWhenTheImagePrefixIsNotLowercaseLettersDigitsAndHyphens(unittest.TestCase):
    prefixes: ClassVar[tuple[str, ...]] = (
        "docker.io/library/scanmylib",
        "docker.io/scanmylib",
        "index.docker.io/library/scanmylib",
        "Scanmylib-dev",
        "scanmylib.dev",
    )

    def setUp(self) -> None:
        layout = make_layout(self)
        self.problems = {
            prefix: find_problems(layout, env={**layout.env, "IMAGE_PREFIX": prefix}) for prefix in self.prefixes
        }

    def test_should_refuse_it(self) -> None:
        for prefix in self.prefixes:
            with self.subTest(prefix):
                self.assertTrue(
                    mentions(self.problems[prefix], "may only contain lowercase letters"), self.problems[prefix]
                )


class TheIsolationProblemsFunctionWhenABindMountUsesAHostPathNoStackMayUse(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        sources = {
            "production's DATA_DIR": (str(layout.production_data_dir), "is production's DATA_DIR"),
            "a directory inside production's DATA_DIR": (
                f"{layout.production_data_dir}/state",
                "is inside production's DATA_DIR",
            ),
            "the parent of production's DATA_DIR": (
                str(layout.production_data_dir.parent),
                "contains production's DATA_DIR",
            ),
            "production's LIBRARY_DIR": (str(layout.library), "is production's LIBRARY_DIR"),
            "production's checkout": (str(layout.primary), "is production's checkout"),
            "production's signing key": (
                f"{layout.production_data_dir}/android/keystore",
                "production's signing key directory",
            ),
            "production's SANDBOX_DIR, read-write": (
                f"{layout.production_data_dir}/sandbox",
                "is production's SANDBOX_DIR",
            ),
            "/run": ("/run", "system directory"),
            "the Docker socket": ("/var/run/docker.sock", "system directory"),
            "the data of Docker": ("/var/lib/docker", "system directory"),
            "/etc": ("/etc", "system directory"),
            "root's home directory": ("/root/.ssh", "system directory"),
            "/tmp": ("/tmp", "is or contains /tmp"),
            "the home directory": (str(layout.home), "contains your home directory"),
            "a directory inside the home directory": (f"{layout.home}/.ssh", "is inside your home directory"),
            "the root directory": ("/", "contains your home directory"),
        }
        self.expected_problems = {row: expected for row, (_, expected) in sources.items()}
        self.problems = {
            row: find_problems(layout, config=build_resolved_compose_config_with_bind_mount(layout, source))
            for row, (source, _) in sources.items()
        }

    def test_should_refuse_it(self) -> None:
        for row, expected in self.expected_problems.items():
            with self.subTest(row):
                self.assertTrue(mentions(self.problems[row], expected), self.problems[row])


class TheIsolationProblemsFunctionWhenHomePointsElsewhere(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        elsewhere = layout.base / "elsewhere-home"
        self.enterContext(mock.patch.dict(os.environ, {"HOME": str(elsewhere)}))
        self.data_dirs = {
            "in the home directory of the password database": f"{layout.home}/dev",
            "in $HOME": f"{elsewhere}/dev",
        }
        self.problems = {
            row: find_problems(layout, env={**layout.env, "DATA_DIR": data_dir})
            for row, data_dir in self.data_dirs.items()
        }

    def test_should_refuse_a_data_dir_in_either_home_directory(self) -> None:
        for row in self.data_dirs:
            with self.subTest(row):
                self.assertTrue(mentions(self.problems[row], "is inside your home directory"), self.problems[row])


class TheIsolationProblemsFunctionWhenABindMountLiesOutsideTheStacksDataDir(unittest.TestCase):
    mounts: ClassVar[Mapping[str, bool]] = types.MappingProxyType({"read-write": False, "read-only": True})

    def setUp(self) -> None:
        layout = make_layout(self)
        elsewhere = f"{layout.base}/elsewhere"
        self.problems = {
            row: find_problems(
                layout, config=build_resolved_compose_config_with_bind_mount(layout, elsewhere, read_only=read_only)
            )
            for row, read_only in self.mounts.items()
        }

    def test_should_refuse_it(self) -> None:
        for row in self.mounts:
            with self.subTest(row):
                self.assertTrue(mentions(self.problems[row], "is not inside the stack's DATA_DIR"), self.problems[row])


class TheIsolationProblemsFunctionWhenAPathOfTheEnvLiesOutsideTheStacksDataDir(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        paths = {
            "LIBRARY_DIR in /tmp": ("LIBRARY_DIR", "/tmp"),
            "LIBRARY_DIR elsewhere": ("LIBRARY_DIR", f"{layout.base}/library2"),
            "ANDROID_DIR elsewhere": ("ANDROID_DIR", f"{layout.base}/android"),
            "SANDBOX_SETUP_DIR elsewhere": ("SANDBOX_SETUP_DIR", f"{layout.base}/sandbox"),
            "SANDBOX_DIR in /tmp": ("SANDBOX_DIR", "/tmp"),
            "ANDROID_KEYSTORE_DIR elsewhere": ("ANDROID_KEYSTORE_DIR", f"{layout.base}/keys"),
            "LIBRARY_DIR in the home directory": ("LIBRARY_DIR", f"{layout.home}/.ssh"),
        }
        self.keys = {row: key for row, (key, _) in paths.items()}
        self.problems = {
            row: find_problems(layout, env={**layout.env, key: value}) for row, (key, value) in paths.items()
        }

    def test_should_refuse_it_naming_its_key(self) -> None:
        for row, key in self.keys.items():
            with self.subTest(row):
                self.assertTrue(mentions(self.problems[row], f"{key} in .env"), self.problems[row])


class TheIsolationProblemsFunctionWhenTheDataDirCannotBeTheStacksOwn(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        data_dirs = {
            "/tmp": ("/tmp", "is or contains /tmp"),
            "a system directory": ("/var/tmp/dev", "system directory"),
            "the home directory": (f"{layout.home}/scanmylib-dev", "is inside your home directory"),
            "a relative path": ("relative/dev", "not an absolute path"),
        }
        self.expected_problems = {row: expected for row, (_, expected) in data_dirs.items()}
        self.problems = {
            row: find_problems(layout, env={**layout.env, "DATA_DIR": data_dir})
            for row, (data_dir, _) in data_dirs.items()
        }

    def test_should_refuse_it(self) -> None:
        for row, expected in self.expected_problems.items():
            with self.subTest(row):
                self.assertTrue(mentions(self.problems[row], expected), self.problems[row])


class TheIsolationProblemsFunctionWhenTheEnvHasNoDataDir(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        env = {key: value for key, value in layout.env.items() if key != "DATA_DIR"}
        self.problems = find_problems(layout, env=env)

    def test_should_refuse_it(self) -> None:
        self.assertTrue(mentions(self.problems, "no DATA_DIR in .env"), self.problems)


class TheIsolationProblemsFunctionWhenABindMountSharesProductionsModelsReadOnly(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        config = build_resolved_compose_config_with_bind_mount(
            layout, f"{layout.production_data_dir}/sandbox/models", read_only=True
        )
        self.problems = find_problems(layout, config=config)

    def test_should_find_none(self) -> None:
        self.assertEqual(self.problems, [])


class TheIsolationProblemsFunctionWhenABindMountSharesProductionsDataDirReadOnly(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        self.problems = find_problems(
            layout,
            config=build_resolved_compose_config_with_bind_mount(
                layout, str(layout.production_data_dir), read_only=True
            ),
        )

    def test_should_refuse_it_as_production_s_data_dir(self) -> None:
        self.assertTrue(mentions(self.problems, "is production's DATA_DIR"), self.problems)

    def test_should_refuse_it_as_a_directory_that_holds_production_s_sandbox_since_only_the_models_are_shared(
        self,
    ) -> None:
        self.assertTrue(mentions(self.problems, "contains production's SANDBOX_DIR"), self.problems)


class TheIsolationProblemsFunctionWhenABindMountThatDockerNeverCreatesIsMissing(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        self.problems = find_problems(
            layout, config=build_resolved_compose_config_with_bind_mount(layout, "/nonexistent/x", create=False)
        )

    def test_should_find_none_since_docker_never_mounts_it_as_the_placeholder_of_ocr_setup(self) -> None:
        self.assertEqual(self.problems, [])


class TheIsolationProblemsFunctionWhenABindMountThatDockerCreatesIsMissing(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        self.problems = find_problems(
            layout, config=build_resolved_compose_config_with_bind_mount(layout, f"{layout.base}/missing", create=True)
        )

    def test_should_refuse_it_outside_the_stack_s_data_dir(self) -> None:
        self.assertTrue(mentions(self.problems, "is not inside the stack's DATA_DIR"), self.problems)


@unittest.skipIf(os.getuid() == 0, "root sees inside a directory that no one may read")
class TheIsolationProblemsFunctionWhenABindMountLiesWhereThisUserCannotSee(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        unreadable_directory = layout.base / "unreadable"
        unreadable_directory.mkdir()
        unreadable_directory.chmod(0o000)
        self.addCleanup(unreadable_directory.chmod, 0o755)
        self.problems = find_problems(
            layout,
            config=build_resolved_compose_config_with_bind_mount(layout, f"{unreadable_directory}/x", create=False),
        )

    def test_should_check_it_as_a_path_that_exists_since_it_may_exist_for_the_docker_daemon(self) -> None:
        self.assertTrue(mentions(self.problems, "is not inside the stack's DATA_DIR"), self.problems)


class TheIsolationProblemsFunctionWhenProductionsContainersRun(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        moved_library = layout.development_data_dir / "moved-library"
        container = {
            "Name": "/scanmylib-api-1",
            "Config": {
                "Image": "scanmylib-api:latest",
                "Labels": {"com.docker.compose.project": "scanmylib", stack.WORKING_DIR_LABEL: str(layout.primary)},
            },
            "Mounts": [{"Type": "bind", "Source": str(moved_library), "Destination": "/library"}],
            "HostConfig": {"PortBindings": {"8765/tcp": [{"HostIp": "", "HostPort": "9999"}]}},
        }
        self.problems_of_the_mount = find_problems(
            layout,
            config=build_resolved_compose_config_with_bind_mount(layout, str(moved_library)),
            containers=[container],
        )
        self.problems_of_the_port = find_problems(
            layout,
            config=build_resolved_compose_config_with_settings(layout, ports=[{"target": 8765, "published": "9999"}]),
            containers=[container],
        )

    def test_should_refuse_a_path_they_mount(self) -> None:
        self.assertTrue(
            mentions(self.problems_of_the_mount, "mount /library of scanmylib-api-1"), self.problems_of_the_mount
        )

    def test_should_refuse_a_port_they_publish(self) -> None:
        self.assertTrue(mentions(self.problems_of_the_port, "publishes port 9999"), self.problems_of_the_port)


class TheIsolationProblemsFunctionWhenProductionRunsFromAnotherCheckout(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        moved = layout.base / "moved-checkout"
        moved.mkdir()
        (moved / ".env").write_text(f"COMPOSE_PROJECT_NAME=scanmylib\nDATA_DIR={layout.base}/moved-data\n")
        container = {"Name": "/scanmylib-api-1", "Config": {"Labels": {stack.WORKING_DIR_LABEL: str(moved)}}}
        self.problems_of_the_checkout = find_problems(
            layout, config=build_resolved_compose_config_with_bind_mount(layout, str(moved)), containers=[container]
        )
        self.problems_of_the_data_dir = find_problems(
            layout, env={**layout.env, "DATA_DIR": f"{layout.base}/moved-data"}, containers=[container]
        )

    def test_should_refuse_that_checkout_as_production_s_whatever_dev_scanmylib_holds(self) -> None:
        self.assertTrue(
            mentions(self.problems_of_the_checkout, "is production's checkout"), self.problems_of_the_checkout
        )

    def test_should_refuse_the_data_dir_of_its_env(self) -> None:
        self.assertTrue(
            mentions(self.problems_of_the_data_dir, "is production's DATA_DIR"), self.problems_of_the_data_dir
        )


class TheIsolationProblemsFunctionWhenAPathTheScriptsUseIsNotTheStacksOwn(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        paths = {
            "production's DATA_DIR": ("DATA_DIR", str(layout.production_data_dir), "DATA_DIR in .env"),
            "production's ANDROID_DIR": ("ANDROID_DIR", f"{layout.production_data_dir}/android", "ANDROID_DIR in .env"),
            "production's sandbox to set up": (
                "SANDBOX_SETUP_DIR",
                f"{layout.production_data_dir}/sandbox",
                "SANDBOX_SETUP_DIR in .env",
            ),
            "a directory holding production's signing key": (
                "ANDROID_KEYSTORE_DIR",
                str(layout.production_data_dir / "android"),
                "ANDROID_KEYSTORE_DIR in .env",
            ),
            "a directory holding production's sandbox": (
                "SANDBOX_DIR",
                str(layout.production_data_dir),
                "SANDBOX_DIR in .env",
            ),
            "a relative LIBRARY_DIR": ("LIBRARY_DIR", "relative/library", "not an absolute path"),
        }
        self.expected_problems = {row: expected for row, (_, _, expected) in paths.items()}
        self.problems = {
            row: find_problems(layout, env={**layout.env, key: value}) for row, (key, value, _) in paths.items()
        }

    def test_should_refuse_it(self) -> None:
        for row, expected in self.expected_problems.items():
            with self.subTest(row):
                self.assertTrue(mentions(self.problems[row], expected), self.problems[row])


class TheIsolationProblemsFunctionWhenTheEnvAsksForTheReleaseApp(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        self.problems = find_problems(layout, env={**layout.env, "APP_VARIANT": "release"})

    def test_should_refuse_it_since_only_production_builds_the_release_app(self) -> None:
        self.assertTrue(mentions(self.problems, "only production builds the release app"), self.problems)


class TheIsolationProblemsFunctionWhenTheEnvNamesAnUnknownOcrService(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        self.problems = find_problems(layout, env={**layout.env, "OCR_SERVICE": "other"})

    def test_should_refuse_it_naming_the_ocr_services(self) -> None:
        self.assertTrue(mentions(self.problems, "expected ocr or ocr-fake"), self.problems)


class TheIsolationProblemsFunctionWhenTheEnvNamesAnotherProjectThanDockerComposeResolves(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        self.problems = find_problems(layout, env={**layout.env, "COMPOSE_PROJECT_NAME": "scanmylib-dev2"})

    def test_should_refuse_it_naming_the_project_of_the_env(self) -> None:
        self.assertTrue(mentions(self.problems, ".env says 'scanmylib-dev2'"), self.problems)


class TheIsolationProblemsFunctionWhenAServiceSettingIsOutsideTheAllowlist(unittest.TestCase):
    settings: ClassVar[Mapping[str, tuple[stack.JsonObject, str]]] = types.MappingProxyType(
        {
            "privileged": ({"privileged": True}, "privileged is not allowed"),
            "cap_add": ({"cap_add": ["SYS_ADMIN"]}, "cap_add is not allowed"),
            "volumes_from": ({"volumes_from": ["container:scanmylib-api-1"]}, "volumes_from is not allowed"),
            "use_api_socket": ({"use_api_socket": True}, "use_api_socket is not allowed"),
            "pid": ({"pid": "host"}, "pid is not allowed"),
            "ipc": ({"ipc": "host"}, "ipc is not allowed"),
            "uts": ({"uts": "host"}, "uts is not allowed"),
            "userns_mode": ({"userns_mode": "host"}, "userns_mode is not allowed"),
            "cgroup": ({"cgroup": "host"}, "cgroup is not allowed"),
            "labels": ({"labels": {"com.docker.compose.project": "scanmylib"}}, "labels is not allowed"),
            "env_file": ({"env_file": [{"path": "/home/x/.env"}]}, "env_file is not allowed"),
            "label_file": ({"label_file": ["/home/x/labels"]}, "label_file is not allowed"),
            "the host's network": ({"network_mode": "host"}, "network_mode host"),
            "a container's network": (
                {"network_mode": "container:scanmylib-ocr-1"},
                "network_mode container:scanmylib-ocr-1",
            ),
            "production's network": ({"network_mode": "scanmylib_default"}, "network_mode scanmylib_default"),
            "the bridge network": ({"network_mode": "bridge"}, "network_mode bridge"),
            "the network of the service itself": ({"network_mode": "service:api"}, "network_mode service:api"),
            "the network of a missing service": ({"network_mode": "service:missing"}, "network_mode service:missing"),
            "a network of another stack": (
                {"networks": {"elsewhere": None}},
                "the network elsewhere is not one of the stack's",
            ),
            "no seccomp profile": ({"security_opt": ["seccomp=unconfined"]}, "security_opt seccomp=unconfined"),
            "no AppArmor profile": ({"security_opt": ["apparmor=unconfined"]}, "security_opt apparmor=unconfined"),
            "a device of the host": (
                {"devices": [{"source": "/dev/sda", "target": "/dev/sda", "permissions": "rwm"}]},
                "device /dev/sda",
            ),
            "the GPU at another path": (
                {"devices": [{"source": "nvidia.com/gpu=all", "target": "/dev/x"}]},
                "device nvidia.com/gpu=all",
            ),
            "production's container name": ({"container_name": "scanmylib-api-1"}, "container_name scanmylib-api-1"),
        }
    )

    def setUp(self) -> None:
        layout = make_layout(self)
        self.problems = {
            row: find_problems(layout, config=build_resolved_compose_config_with_settings(layout, **settings))
            for row, (settings, _) in self.settings.items()
        }

    def test_should_refuse_it(self) -> None:
        for row, (_, expected) in self.settings.items():
            with self.subTest(row):
                self.assertTrue(mentions(self.problems[row], expected), self.problems[row])


class TheIsolationProblemsFunctionWhenTheNetworkModeIsTheStacksOwn(unittest.TestCase):
    network_modes: ClassVar[tuple[str, ...]] = ("none", "service:ocr")

    def setUp(self) -> None:
        layout = make_layout(self)
        self.problems = {
            network_mode: find_problems(
                layout, config=build_resolved_compose_config_with_settings(layout, network_mode=network_mode)
            )
            for network_mode in self.network_modes
        }

    def test_should_find_none(self) -> None:
        for network_mode in self.network_modes:
            with self.subTest(network_mode):
                self.assertEqual(self.problems[network_mode], [])


class TheIsolationProblemsFunctionWhenOnlyTheConfigurationWithoutInterpolationShowsASetting(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        raw = build_resolved_compose_config(layout)
        raw["services"]["api"]["env_file"] = [{"path": f"{layout.home}/.aws/credentials", "required": True}]
        self.problems = find_problems(layout, raw=raw)

    def test_should_refuse_it_since_docker_compose_config_merges_it_into_another_setting(self) -> None:
        self.assertTrue(mentions(self.problems, "service api: env_file is not allowed"), self.problems)


class TheIsolationProblemsFunctionWhenTheConfigurationWithoutInterpolationIsMissing(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        self.problems = find_problems(layout, raw={"services": {}})

    def test_should_refuse_the_stack(self) -> None:
        self.assertTrue(mentions(self.problems, "no configuration without interpolation"), self.problems)


class TheIsolationProblemsFunctionWhenTheComposeFileIncludesAnother(unittest.TestCase):
    compose_files: ClassVar[Mapping[str, str]] = types.MappingProxyType(
        {
            "in block style, with an env_file": "include:\n  - path: x.yaml\n    env_file: /home/x/.env\n",
            "in flow style": '{"include": ["x.yaml"]}',
            "quoted, after another key": "name: x\n'include' :\n  - x.yaml\n",
        }
    )

    def setUp(self) -> None:
        layout = make_layout(self)
        self.problems: dict[str, list[str]] = {}
        for index, (row, text) in enumerate(self.compose_files.items()):
            compose = layout.base / f"compose-{index}.yaml"
            compose.write_text(text)
            self.problems[row] = find_problems(layout, compose_file=str(compose))

    def test_should_refuse_it_since_its_env_file_feeds_host_files_into_what_it_includes(self) -> None:
        for row in self.compose_files:
            with self.subTest(row):
                self.assertTrue(mentions(self.problems[row], "include is not allowed"), self.problems[row])


class TheIsolationProblemsFunctionWhenTheComposeFileOnlyMentionsInclude(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        compose = layout.base / "compose.yaml"
        compose.write_text("# include: a comment\nservices:\n  api:\n    command: [sh, -c, 'echo include']\n")
        self.problems = find_problems(layout, compose_file=str(compose))

    def test_should_find_none(self) -> None:
        self.assertEqual(self.problems, [])


class TheIsolationProblemsFunctionWhenABuildSettingIsNotAllowed(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        server = f"{layout.worktree}/server"
        builds: dict[str, tuple[stack.JsonObject, str]] = {
            "a context in the home directory": (
                {"context": "/home/someone"},
                "build context /home/someone is not inside the project directory",
            ),
            "a remote context": ({"context": "https://example.com/repo.git"}, "is not inside the project directory"),
            "an additional context in /etc": (
                {"context": server, "additional_contexts": {"x": "/etc"}},
                "build additional context x /etc",
            ),
            "an additional context from an image": (
                {"context": server, "additional_contexts": {"x": "docker-image://scanmylib-api"}},
                "additional context x",
            ),
            "ssh": ({"context": server, "ssh": ["default"]}, "build setting ssh"),
            "tags": ({"context": server, "tags": ["scanmylib-api:latest"]}, "build setting tags"),
            "secrets": ({"context": server, "secrets": ["token"]}, "build setting secrets"),
            "a network": ({"context": server, "network": "host"}, "build setting network"),
        }
        self.expected_problems = {row: expected for row, (_, expected) in builds.items()}
        self.problems = {
            row: find_problems(layout, config=build_resolved_compose_config_with_settings(layout, build=build))
            for row, (build, _) in builds.items()
        }

    def test_should_refuse_it(self) -> None:
        for row, expected in self.expected_problems.items():
            with self.subTest(row):
                self.assertTrue(mentions(self.problems[row], expected), self.problems[row])


class TheIsolationProblemsFunctionWhenANetworkAVolumeOrATopLevelSettingIsNotTheStacksOwn(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        configs = {
            "production's network": (
                build_resolved_compose_config(layout, networks={"default": {"name": "scanmylib_default"}}),
                "network default",
            ),
            "an external network": (
                build_resolved_compose_config(
                    layout, networks={"default": {"name": "scanmylib-dev_default", "external": True}}
                ),
                "network default",
            ),
            "a volume that binds a host path": (
                build_resolved_compose_config(
                    layout,
                    volumes={
                        "data": {
                            "name": "scanmylib-dev_data",
                            "driver_opts": {"type": "none", "o": "bind", "device": str(layout.home)},
                        }
                    },
                ),
                "driver and driver_opts",
            ),
            "a macvlan network": (
                build_resolved_compose_config(
                    layout,
                    networks={
                        "default": {
                            "name": "scanmylib-dev_default",
                            "driver": "macvlan",
                            "driver_opts": {"parent": "eth0"},
                        }
                    },
                ),
                "network default: driver and driver_opts",
            ),
            "an ipvlan network": (
                build_resolved_compose_config(
                    layout, networks={"default": {"name": "scanmylib-dev_default", "driver": "ipvlan"}}
                ),
                "network default: driver and driver_opts",
            ),
            "production's volume": (
                build_resolved_compose_config(layout, volumes={"data": {"name": "scanmylib_data"}}),
                "volume data (scanmylib_data) is not the stack's own",
            ),
            "a top-level secret": (
                build_resolved_compose_config(
                    layout, secrets={"token": {"file": f"{layout.production_data_dir}/state/token"}}
                ),
                "secrets (top level)",
            ),
            "an npipe mount": (
                build_resolved_compose_config_with_settings(
                    layout, volumes=[{"type": "npipe", "source": "x", "target": "/x"}]
                ),
                "npipe mount",
            ),
        }
        self.expected_problems = {row: expected for row, (_, expected) in configs.items()}
        self.problems = {row: find_problems(layout, config=config) for row, (config, _) in configs.items()}

    def test_should_refuse_it(self) -> None:
        for row, expected in self.expected_problems.items():
            with self.subTest(row):
                self.assertTrue(mentions(self.problems[row], expected), self.problems[row])


class TheProductionIdentityFunctionWhenProductionsEnvBreaksTheFormat(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        (layout.primary / ".env").write_text("DATA_DIR=/data/x # comment\n")
        self.identify_production = functools.partial(stack.production_identity, layout.primary, [])

    def test_should_refuse_it_since_production_is_to_be_fixed_first(self) -> None:
        self.assertRaisesRegex(stack.EnvError, "production's .env", self.identify_production)


class TheMainFunctionWhenAskedToCheckPathsOfTheirOwn(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        self.exit_code, self.error_text = run_check_paths(
            f"DATA_DIR={layout.base}/ci", f"ANDROID_DIR={layout.base}/ci/a"
        )

    def test_should_accept_them_without_a_word(self) -> None:
        self.assertEqual((self.exit_code, self.error_text), (0, ""))


class TheMainFunctionWhenAskedToCheckAPathOfProductions(unittest.TestCase):
    def setUp(self) -> None:
        self.layout = make_layout(self)
        self.exit_code, self.error_text = run_check_paths(
            f"DATA_DIR={self.layout.base}/ci", f"ANDROID_DIR={self.layout.production_data_dir}/android"
        )

    def test_should_refuse_it_naming_it_as_production_s(self) -> None:
        self.assertEqual(self.exit_code, 1)
        self.assertIn(
            f"ANDROID_DIR: {self.layout.production_data_dir}/android is production's ANDROID_DIR", self.error_text
        )


class TheMainFunctionWhenAskedToCheckPathsInTheHomeDirectory(unittest.TestCase):
    def setUp(self) -> None:
        self.layout = make_layout(self)
        self.exit_code, self.error_text = run_check_paths(
            f"DATA_DIR={self.layout.home}/ci", f"ANDROID_DIR={self.layout.home}/.config"
        )

    def test_should_refuse_the_data_dir(self) -> None:
        self.assertEqual(self.exit_code, 1)
        self.assertIn("DATA_DIR: ", self.error_text)

    def test_should_refuse_the_android_dir_saying_it_is_inside_the_home_directory(self) -> None:
        self.assertIn(f"ANDROID_DIR: {self.layout.home}/.config is inside your home directory", self.error_text)


class TheMainFunctionWhenAskedToCheckPathsInsideTheRunnerTemp(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        runner_temp = f"{layout.home}/work/_temp"
        self.exit_code, self.error_text = run_check_paths(
            "--runner-temp", runner_temp, f"DATA_DIR={runner_temp}/ci", f"ANDROID_DIR={runner_temp}/ci/android"
        )

    def test_should_accept_them_since_github_s_runner_keeps_its_temporary_directory_in_its_home_directory(
        self,
    ) -> None:
        self.assertEqual((self.exit_code, self.error_text), (0, ""))


class TheMainFunctionWhenAskedToCheckAPathOfTheHomeDirectoryOutsideTheRunnerTemp(unittest.TestCase):
    def setUp(self) -> None:
        self.layout = make_layout(self)
        runner_temp = f"{self.layout.home}/work/_temp"
        self.exit_code, self.error_text = run_check_paths(
            "--runner-temp", runner_temp, f"DATA_DIR={runner_temp}/ci", f"ANDROID_DIR={self.layout.home}/.config"
        )

    def test_should_refuse_it_saying_it_is_inside_the_home_directory(self) -> None:
        self.assertEqual(self.exit_code, 1)
        self.assertIn(f"ANDROID_DIR: {self.layout.home}/.config is inside your home directory", self.error_text)


class TheMainFunctionWhenTheRunnerTempIsTheHomeDirectory(unittest.TestCase):
    def setUp(self) -> None:
        layout = make_layout(self)
        self.exit_code, self.error_text = run_check_paths(
            "--runner-temp", str(layout.home), f"DATA_DIR={layout.home}/ci"
        )

    def test_should_refuse_the_runner_temp(self) -> None:
        self.assertEqual(self.exit_code, 1)
        self.assertIn("RUNNER_TEMP: ", self.error_text)


class TheComposeCommandProblemsFunctionWhenTheCommandStaysInTheStack(unittest.TestCase):
    commands: ClassVar[tuple[tuple[str, ...], ...]] = (
        ("ps",),
        ("up", "-d", "api"),
        ("exec", "api", "sh"),
        ("exec", "-T", "-u", "1000", "api", "id"),
        ("run", "--rm", "-e", "X=1", "api", "pytest", "-v", "-p", "no:cacheprovider"),
        ("run", "-dT", "--entrypoint=sh", "api"),
        ("run", "-eX=1", "--rm", "api"),
        ("build", "--no-cache", "api"),
        ("build", "api", "--no-cache"),
        ("logs", "-f", "api"),
        ("down", "-v"),
        ("config",),
        ("config", "--format", "json", "--no-interpolate"),
        ("config", "--hash", "api"),
        ("up", "-d", "--wait", "--wait-timeout", "60", "api", "ocr-fake"),
        ("up", "api", "-d", "--timeout", "5"),
        ("restart", "-t", "5", "api"),
        ("start", "ocr"),
        ("create", "--no-build", "--", "api"),
    )

    def setUp(self) -> None:
        self.problems = {command: stack.compose_command_problems(list(command)) for command in self.commands}

    def test_should_find_none(self) -> None:
        for command in self.commands:
            with self.subTest(" ".join(command)):
                self.assertEqual(self.problems[command], [])


class TheComposeCommandProblemsFunctionWhenTheCommandLineDoesNotStartWithACommand(unittest.TestCase):
    commands: ClassVar[Mapping[str, tuple[str, ...]]] = types.MappingProxyType(
        {
            "-p": ("-p", "scanmylib", "down"),
            "--project-name": ("--project-name=scanmylib", "down"),
            "--file": ("--file", "x.yaml", "ps"),
            "nothing": (),
        }
    )

    def setUp(self) -> None:
        self.problems = {row: stack.compose_command_problems(list(command)) for row, command in self.commands.items()}

    def test_should_refuse_it_since_a_global_option_could_choose_another_stack(self) -> None:
        for row in self.commands:
            with self.subTest(row):
                self.assertIn("no global option", "".join(self.problems[row][:1]), self.problems[row])


class TheComposeCommandProblemsFunctionWhenTheCommandCouldReachOutsideTheStack(unittest.TestCase):
    commands: ClassVar[tuple[str, ...]] = (
        "cp",
        "export",
        "commit",
        "push",
        "pull",
        "publish",
        "watch",
        "bridge",
        "scale",
    )

    def setUp(self) -> None:
        self.problems = {command: stack.compose_command_problems([command, "api"]) for command in self.commands}

    def test_should_refuse_it(self) -> None:
        for command in self.commands:
            with self.subTest(command):
                problems = self.problems[command]
                self.assertIn(f"docker compose {command} is not allowed", "".join(problems[:1]), problems)


class TheComposeCommandProblemsFunctionWhenAnOptionGivesAContainerMoreThanComposeYamlDoes(unittest.TestCase):
    commands: ClassVar[Mapping[str, tuple[tuple[str, ...], str]]] = types.MappingProxyType(
        {
            "run -v": (("run", "-v", "/:/host", "api"), "run -v"),
            "run --volume=": (("run", "--volume=/home:/h", "api"), "run --volume"),
            "run -v among other flags": (("run", "-dv", "/:/host", "api"), "run -v"),
            "run -p": (("run", "-p", "8765:8765", "api"), "run -p"),
            "run --publish": (("run", "--publish", "8765:8765", "api"), "run --publish"),
            "run --cap-add": (("run", "--cap-add", "SYS_ADMIN", "api"), "run --cap-add"),
            "run --env-from-file": (("run", "--env-from-file", "/home/x/.env", "api"), "run --env-from-file"),
            "run -l": (("run", "-l", "com.docker.compose.project=scanmylib", "api"), "run -l"),
            "run --name": (("run", "--name", "scanmylib-api-1", "api"), "run --name"),
            "run -v after allowed options": (("run", "--rm", "-e", "X", "-v", "/:/h", "api"), "run -v"),
            "exec --privileged": (("exec", "--privileged", "api", "sh"), "exec --privileged"),
            "build --ssh": (("build", "--ssh", "default", "api"), "build --ssh"),
            "build --push": (("build", "--push"), "build --push"),
            "build --ssh after the service, which docker compose reads as an option too": (
                ("build", "api", "--ssh", "default=/home/x/.ssh/id_ed25519"),
                "build --ssh",
            ),
            "build --push after the service": (("build", "api", "--push"), "build --push"),
            "build --push after the services and another option": (
                ("build", "api", "ocr", "-q", "--push"),
                "build --push",
            ),
            "config -o": (("config", "-o", "/home/x/Dev/scanmylib/.env"), "config -o"),
            "config --output=": (("config", "--output=/home/x/.bashrc"), "config --output"),
            "config --output after an allowed option": (
                ("config", "--format", "json", "--output", "x"),
                "config --output",
            ),
            "up --watch": (("up", "-d", "api", "--watch"), "up --watch"),
            "up -w among other flags": (("up", "-dw", "api"), "up -w"),
            "up --scale, which starts the services it names, listed or not": (
                ("up", "-d", "api", "ocr", "--scale", "ocr-fake=1"),
                "up --scale",
            ),
            "create --scale=": (("create", "--scale=ocr-fake=1", "api"), "create --scale"),
        }
    )

    def setUp(self) -> None:
        self.problems = {
            row: stack.compose_command_problems(list(command)) for row, (command, _) in self.commands.items()
        }

    def test_should_refuse_it_naming_the_option(self) -> None:
        for row, (_, expected) in self.commands.items():
            with self.subTest(row):
                self.assertIn(expected, "".join(self.problems[row][:1]), self.problems[row])


class TheComposeCommandProblemsFunctionWhenAStartingCommandNamesNoService(unittest.TestCase):
    commands: ClassVar[tuple[tuple[str, ...], ...]] = (
        ("up", "-d"),
        ("up", "-d", "--wait"),
        ("restart",),
        ("start",),
        ("create", "--"),
    )

    def setUp(self) -> None:
        self.problems = {command: stack.compose_command_problems(list(command)) for command in self.commands}

    def test_should_refuse_it_asking_to_name_them_since_both_ocr_services_would_start(self) -> None:
        for command in self.commands:
            with self.subTest(" ".join(command)):
                self.assertIn("name them", "".join(self.problems[command][:1]), self.problems[command])


class TheComposeCommandProblemsFunctionWhenAStartingCommandNamesBothOcrServices(unittest.TestCase):
    commands: ClassVar[tuple[tuple[str, ...], ...]] = (
        ("up", "-d", "api", "ocr", "ocr-fake"),
        ("start", "ocr-fake", "ocr"),
        ("up", "ocr", "--", "ocr-fake"),
    )

    def setUp(self) -> None:
        self.problems = {command: stack.compose_command_problems(list(command)) for command in self.commands}

    def test_should_refuse_it_since_both_serve_the_same_socket(self) -> None:
        for command in self.commands:
            with self.subTest(" ".join(command)):
                self.assertIn("never start both", "".join(self.problems[command][:1]), self.problems[command])


class TheComposeCommandProblemsFunctionWhenProductionOperatesItsContainers(unittest.TestCase):
    commands: ClassVar[tuple[tuple[str, ...], ...]] = (
        ("ps",),
        ("logs", "-f", "api", "ocr"),
        ("restart", "api"),
        ("up", "-d", "--no-build", "api", "ocr"),
        ("up", "-d"),
        ("restart",),
        ("stop", "api", "ocr"),
        ("down",),
    )

    def setUp(self) -> None:
        self.problems = {
            command: stack.compose_command_problems(list(command), production=True) for command in self.commands
        }

    def test_should_find_none(self) -> None:
        for command in self.commands:
            with self.subTest(" ".join(command)):
                self.assertEqual(self.problems[command], [])


class TheComposeCommandProblemsFunctionWhenProductionWouldChangeOtherwiseThanThroughDeploySh(unittest.TestCase):
    commands: ClassVar[Mapping[str, tuple[tuple[str, ...], str]]] = types.MappingProxyType(
        {
            "build": (("build", "api"), "scripts/deploy.sh"),
            "run": (("run", "api", "sh"), "scripts/deploy.sh"),
            "up --build": (("up", "-d", "--build"), "--build"),
            "exec --privileged": (("exec", "--privileged", "api", "sh"), "--privileged"),
            "cp": (("cp", "api:/state/token", "."), "not allowed"),
            "the fake OCR": (("up", "-d", "ocr-fake"), "fake OCR"),
            "config -o": (("config", "-o", ".env"), "config -o"),
        }
    )

    def setUp(self) -> None:
        self.problems = {
            row: stack.compose_command_problems(list(command), production=True)
            for row, (command, _) in self.commands.items()
        }

    def test_should_refuse_it(self) -> None:
        for row, (_, expected) in self.commands.items():
            with self.subTest(row):
                self.assertIn(expected, "".join(self.problems[row][:1]), self.problems[row])


if __name__ == "__main__":
    unittest.main()
