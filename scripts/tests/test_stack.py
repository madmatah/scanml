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
from pathlib import Path
from typing import ClassVar
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import stack

DEV_ENV = """\
# A development stack.
COMPOSE_PROJECT_NAME=scanmylib-dev
IMAGE_PREFIX=scanmylib-dev

DATA_DIR={dev}
SANDBOX_DIR={prod}/sandbox
ANDROID_DIR={dev}/android
ANDROID_KEYSTORE_DIR={prod}/android/keystore
LIBRARY_DIR={dev}/library
API_PORT=8770
PUBLIC_URL=http://192.168.1.10:8770
OCR_SERVICE=ocr-fake
APP_VARIANT=dev
"""


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


class IsolationTest(unittest.TestCase):
    """isolation_problems() on configurations shaped like `docker compose config --format json`."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(os.path.realpath(directory.name))
        self.prod = self.base / "prod"
        self.dev = self.base / "prod-dev"
        self.home = self.base / "home"
        self.primary = self.home / "Dev" / "scanmylib"
        self.library = self.home / "Documents" / "ScanMyLib"
        self.worktree = self.base / "worktree"
        self.primary.mkdir(parents=True)
        fake_home(self, self.home)
        (self.primary / ".env").write_text(
            f"COMPOSE_PROJECT_NAME=scanmylib\nIMAGE_PREFIX=scanmylib\nDATA_DIR={self.prod}\n"
            f"SANDBOX_DIR={self.prod}/sandbox\nANDROID_DIR={self.prod}/android\nLIBRARY_DIR={self.library}\n"
            f"API_PORT=8765\nSANDBOX_SETUP_DIR={self.prod}/sandbox\n"
        )
        self.env = dict(
            line.split("=", 1)
            for line in DEV_ENV.format(dev=self.dev, prod=self.prod).splitlines()
            if line and not line.startswith("#")
        )

    def config(self, **changes: object) -> stack.JsonObject:
        dev, prod, worktree = self.dev, self.prod, self.worktree
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
                        {"type": "bind", "source": f"{dev}/library", "target": "/library", "bind": created},
                        {"type": "bind", "source": f"{dev}/state", "target": "/state", "bind": created},
                        {"type": "bind", "source": f"{dev}/run", "target": "/run/scanmylib", "bind": created},
                        {
                            "type": "bind",
                            "source": f"{dev}/app",
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
                            "source": f"{prod}/sandbox",
                            "target": "/opt/sandbox",
                            "read_only": True,
                            "bind": created,
                        },
                        {"type": "bind", "source": f"{dev}/run", "target": "/run/scanmylib", "bind": created},
                        {"type": "bind", "source": f"{dev}/ocr-cache", "target": "/var/cache/ocr", "bind": created},
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

    def problems(
        self,
        config: stack.JsonObject | None = None,
        env: dict[str, str] | None = None,
        containers: Sequence[stack.JsonObject] = (),
        raw: stack.JsonObject | None = None,
        compose_file: str | None = None,
    ) -> list[str]:
        checkout = stack.production_checkout(list(containers))
        production = stack.production_identity(checkout, list(containers))
        config = config or self.config()
        return stack.isolation_problems(
            env or self.env, config, raw or config, production, str(self.worktree), compose_file
        )

    def assert_refused(
        self,
        pattern: str,
        *,
        config: stack.JsonObject | None = None,
        env: dict[str, str] | None = None,
        containers: Sequence[stack.JsonObject] = (),
        raw: stack.JsonObject | None = None,
        compose_file: str | None = None,
    ) -> None:
        problems = self.problems(config, env, containers, raw, compose_file)
        self.assertTrue(any(pattern in problem for problem in problems), problems)

    def service(self, name: str = "api", **settings: object) -> stack.JsonObject:
        config = self.config()
        config["services"][name].update(settings)
        return config

    def test_the_development_stack_shares_nothing(self) -> None:
        self.assertEqual(self.problems(), [])

    def test_production_project_images_and_ports(self) -> None:
        self.assert_refused("the project is production's", config=self.config(name="scanmylib"))
        self.assert_refused(
            "the image scanmylib-api:dev is production's", config=self.service(image="scanmylib-api:dev")
        )
        self.assert_refused(
            "publishes port 8765", config=self.service(ports=[{"target": 8765, "published": "8760-8770"}])
        )

    def test_image_names_as_docker_reads_them(self) -> None:
        for image in (
            "docker.io/library/scanmylib-api:latest",
            "docker.io/scanmylib-api",
            "index.docker.io/library/scanmylib-api:latest",
        ):
            with self.subTest(image=image):
                self.assert_refused(f"the image {image} is production's", config=self.service(image=image))
        for image in (
            "scanmylib-dev-api:dev",
            "scanmylib-dev-other:latest",
            "docker.io/library/scanmylib-dev-api:latest",
            "busybox:latest",
        ):
            with self.subTest(image=image):
                self.assert_refused("is not one of the stack's own", config=self.service(image=image))
        for prefix in (
            "docker.io/library/scanmylib",
            "docker.io/scanmylib",
            "index.docker.io/library/scanmylib",
            "Scanmylib-dev",
            "scanmylib.dev",
        ):
            with self.subTest(prefix=prefix):
                self.assert_refused("may only contain lowercase letters", env={**self.env, "IMAGE_PREFIX": prefix})

    def bind(self, source: str, read_only: bool = False, service: str = "api", create: bool = True) -> stack.JsonObject:
        config = self.config()
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

    def test_host_paths_of_production(self) -> None:
        cases = [
            (str(self.prod), "is production's DATA_DIR"),
            (f"{self.prod}/state", "is inside production's DATA_DIR"),
            (str(self.prod.parent), "contains production's DATA_DIR"),
            (str(self.library), "is production's LIBRARY_DIR"),
            (str(self.primary), "is production's checkout"),
            (f"{self.prod}/android/keystore", "production's signing key directory"),
            (f"{self.prod}/sandbox", "is production's SANDBOX_DIR"),  # read-write
            ("/run", "system directory"),
            ("/var/run/docker.sock", "system directory"),
            ("/var/lib/docker", "system directory"),
            ("/etc", "system directory"),
            ("/tmp", "is or contains /tmp"),
            (str(self.home), "contains your home directory"),
            (f"{self.home}/.ssh", "is inside your home directory"),
            ("/", "contains your home directory"),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.assert_refused(expected, config=self.bind(source))

    def test_home_from_the_password_database_and_home_variable(self) -> None:
        # $HOME points elsewhere: both home directories are refused.
        elsewhere = self.base / "elsewhere-home"
        with mock.patch.dict(os.environ, {"HOME": str(elsewhere)}):
            for data_dir in (f"{self.home}/dev", f"{elsewhere}/dev"):
                with self.subTest(data_dir=data_dir):
                    self.assert_refused("is inside your home directory", env={**self.env, "DATA_DIR": data_dir})

    def test_every_other_path_is_inside_the_stack_s_data_dir(self) -> None:
        self.assert_refused("is not inside the stack's DATA_DIR", config=self.bind(f"{self.base}/elsewhere"))
        self.assert_refused(
            "is not inside the stack's DATA_DIR", config=self.bind(f"{self.base}/elsewhere", read_only=True)
        )
        for key, value in [
            ("LIBRARY_DIR", "/tmp"),
            ("LIBRARY_DIR", f"{self.base}/library2"),
            ("ANDROID_DIR", f"{self.base}/android"),
            ("SANDBOX_SETUP_DIR", f"{self.base}/sandbox"),
            ("SANDBOX_DIR", "/tmp"),
            ("ANDROID_KEYSTORE_DIR", f"{self.base}/keys"),
            ("LIBRARY_DIR", f"{self.home}/.ssh"),
        ]:
            with self.subTest(key=key, value=value):
                self.assert_refused(f"{key} in .env", env={**self.env, key: value})
        for value, expected in [
            ("/tmp", "is or contains /tmp"),
            ("/var/tmp/dev", "system directory"),
            (f"{self.home}/scanmylib-dev", "is inside your home directory"),
            ("relative/dev", "not an absolute path"),
        ]:
            with self.subTest(data_dir=value):
                self.assert_refused(expected, env={**self.env, "DATA_DIR": value})
        self.assert_refused(
            "no DATA_DIR in .env", env={key: value for key, value in self.env.items() if key != "DATA_DIR"}
        )

    def test_production_sandbox_is_shared_read_only_only(self) -> None:
        self.assertEqual(self.problems(config=self.bind(f"{self.prod}/sandbox/models", read_only=True)), [])
        self.assert_refused("is production's DATA_DIR", config=self.bind(str(self.prod), read_only=True))
        self.assert_refused("contains production's SANDBOX_DIR", config=self.bind(str(self.prod), read_only=True))

    def test_a_bind_mount_docker_would_never_create(self) -> None:
        # The placeholder of ocr-setup: no such path, and docker compose does not create it.
        self.assertEqual(self.problems(config=self.bind("/nonexistent/x", create=False)), [])
        self.assert_refused("is not inside the stack's DATA_DIR", config=self.bind(f"{self.base}/missing", create=True))
        # A path this user cannot see may exist for the Docker daemon.
        if os.getuid() != 0 and not os.access("/root", os.X_OK):
            self.assert_refused("system directory", config=self.bind("/root/.ssh", create=False))

    def test_paths_from_the_running_production_containers(self) -> None:
        elsewhere = self.dev / "moved-library"
        container = {
            "Name": "/scanmylib-api-1",
            "Config": {
                "Image": "scanmylib-api:latest",
                "Labels": {"com.docker.compose.project": "scanmylib", stack.WORKING_DIR_LABEL: str(self.primary)},
            },
            "Mounts": [{"Type": "bind", "Source": str(elsewhere), "Destination": "/library"}],
            "HostConfig": {"PortBindings": {"8765/tcp": [{"HostIp": "", "HostPort": "9999"}]}},
        }
        self.assert_refused(
            "mount /library of scanmylib-api-1", config=self.bind(str(elsewhere)), containers=[container]
        )
        self.assert_refused(
            "publishes port 9999",
            config=self.service(ports=[{"target": 8765, "published": "9999"}]),
            containers=[container],
        )

    def test_production_checkout_from_its_containers(self) -> None:
        # Production runs from another checkout: that one is production's, whatever ~/Dev holds.
        moved = self.base / "moved-checkout"
        moved.mkdir()
        (moved / ".env").write_text(f"COMPOSE_PROJECT_NAME=scanmylib\nDATA_DIR={self.base}/moved-data\n")
        container = {"Name": "/scanmylib-api-1", "Config": {"Labels": {stack.WORKING_DIR_LABEL: str(moved)}}}
        self.assert_refused("is production's checkout", config=self.bind(str(moved)), containers=[container])
        self.assert_refused(
            "is production's DATA_DIR", env={**self.env, "DATA_DIR": f"{self.base}/moved-data"}, containers=[container]
        )

    def test_paths_the_scripts_use(self) -> None:
        for key, value, expected in [
            ("DATA_DIR", str(self.prod), "DATA_DIR in .env"),
            ("ANDROID_DIR", f"{self.prod}/android", "ANDROID_DIR in .env"),
            ("SANDBOX_SETUP_DIR", f"{self.prod}/sandbox", "SANDBOX_SETUP_DIR in .env"),
            ("ANDROID_KEYSTORE_DIR", str(self.prod / "android"), "ANDROID_KEYSTORE_DIR in .env"),
            ("SANDBOX_DIR", str(self.prod), "SANDBOX_DIR in .env"),
            ("LIBRARY_DIR", "relative/library", "not an absolute path"),
        ]:
            with self.subTest(key=key):
                self.assert_refused(expected, env={**self.env, key: value})

    def test_variants_and_services(self) -> None:
        self.assert_refused("only production builds the release app", env={**self.env, "APP_VARIANT": "release"})
        self.assert_refused("expected ocr or ocr-fake", env={**self.env, "OCR_SERVICE": "other"})
        self.assert_refused(".env says 'scanmylib-dev2'", env={**self.env, "COMPOSE_PROJECT_NAME": "scanmylib-dev2"})

    def test_settings_outside_the_allowlist(self) -> None:
        refused_settings: list[tuple[stack.JsonObject, str]] = [
            ({"privileged": True}, "privileged is not allowed"),
            ({"cap_add": ["SYS_ADMIN"]}, "cap_add is not allowed"),
            ({"volumes_from": ["container:scanmylib-api-1"]}, "volumes_from is not allowed"),
            ({"use_api_socket": True}, "use_api_socket is not allowed"),
            ({"pid": "host"}, "pid is not allowed"),
            ({"ipc": "host"}, "ipc is not allowed"),
            ({"uts": "host"}, "uts is not allowed"),
            ({"userns_mode": "host"}, "userns_mode is not allowed"),
            ({"cgroup": "host"}, "cgroup is not allowed"),
            ({"labels": {"com.docker.compose.project": "scanmylib"}}, "labels is not allowed"),
            ({"env_file": [{"path": "/home/x/.env"}]}, "env_file is not allowed"),
            ({"label_file": ["/home/x/labels"]}, "label_file is not allowed"),
            ({"network_mode": "host"}, "network_mode host"),
            ({"network_mode": "container:scanmylib-ocr-1"}, "network_mode container:scanmylib-ocr-1"),
            ({"network_mode": "scanmylib_default"}, "network_mode scanmylib_default"),
            ({"network_mode": "bridge"}, "network_mode bridge"),
            ({"network_mode": "service:api"}, "network_mode service:api"),
            ({"network_mode": "service:missing"}, "network_mode service:missing"),
            ({"networks": {"elsewhere": None}}, "the network elsewhere is not one of the stack's"),
            ({"security_opt": ["seccomp=unconfined"]}, "security_opt seccomp=unconfined"),
            ({"security_opt": ["apparmor=unconfined"]}, "security_opt apparmor=unconfined"),
            ({"devices": [{"source": "/dev/sda", "target": "/dev/sda", "permissions": "rwm"}]}, "device /dev/sda"),
            ({"devices": [{"source": "nvidia.com/gpu=all", "target": "/dev/x"}]}, "device nvidia.com/gpu=all"),
            ({"container_name": "scanmylib-api-1"}, "container_name scanmylib-api-1"),
        ]
        for settings, expected in refused_settings:
            with self.subTest(settings=settings):
                self.assert_refused(expected, config=self.service(**settings))

    def test_network_mode_of_the_stack(self) -> None:
        for network_mode in ("none", "service:ocr"):
            with self.subTest(network_mode=network_mode):
                self.assertEqual(self.problems(config=self.service(network_mode=network_mode)), [])

    def test_settings_that_only_the_configuration_without_interpolation_shows(self) -> None:
        # docker compose config merges env_file into environment: only the raw configuration
        # (--no-interpolate) still has it.
        raw = self.config()
        raw["services"]["api"]["env_file"] = [{"path": f"{self.home}/.aws/credentials", "required": True}]
        self.assert_refused("service api: env_file is not allowed", raw=raw)
        self.assert_refused("no configuration without interpolation", raw={"services": {}})

    def test_include_in_the_compose_file(self) -> None:
        compose = self.base / "compose.yaml"
        for text in (
            "include:\n  - path: x.yaml\n    env_file: /home/x/.env\n",
            '{"include": ["x.yaml"]}',
            "name: x\n'include' :\n  - x.yaml\n",
        ):
            with self.subTest(text=text):
                compose.write_text(text)
                self.assert_refused("include is not allowed", compose_file=str(compose))
        compose.write_text("# include: a comment\nservices:\n  api:\n    command: [sh, -c, 'echo include']\n")
        self.assertEqual(self.problems(compose_file=str(compose)), [])

    def test_build_settings(self) -> None:
        server = f"{self.worktree}/server"
        for build, expected in [
            ({"context": "/home/someone"}, "build context /home/someone is not inside the project directory"),
            ({"context": "https://example.com/repo.git"}, "is not inside the project directory"),
            ({"context": server, "additional_contexts": {"x": "/etc"}}, "build additional context x /etc"),
            ({"context": server, "additional_contexts": {"x": "docker-image://scanmylib-api"}}, "additional context x"),
            ({"context": server, "ssh": ["default"]}, "build setting ssh"),
            ({"context": server, "tags": ["scanmylib-api:latest"]}, "build setting tags"),
            ({"context": server, "secrets": ["token"]}, "build setting secrets"),
            ({"context": server, "network": "host"}, "build setting network"),
        ]:
            with self.subTest(build=build):
                self.assert_refused(expected, config=self.service(build=build))

    def test_networks_volumes_and_top_level_settings(self) -> None:
        self.assert_refused("network default", config=self.config(networks={"default": {"name": "scanmylib_default"}}))
        self.assert_refused(
            "network default",
            config=self.config(networks={"default": {"name": "scanmylib-dev_default", "external": True}}),
        )
        self.assert_refused(
            "driver and driver_opts",
            config=self.config(
                volumes={
                    "data": {
                        "name": "scanmylib-dev_data",
                        "driver_opts": {"type": "none", "o": "bind", "device": str(self.home)},
                    }
                }
            ),
        )
        for network in ({"driver": "macvlan", "driver_opts": {"parent": "eth0"}}, {"driver": "ipvlan"}):
            with self.subTest(network=network):
                self.assert_refused(
                    "network default: driver and driver_opts",
                    config=self.config(networks={"default": {"name": "scanmylib-dev_default", **network}}),
                )
        self.assert_refused(
            "volume data (scanmylib_data) is not the stack's own",
            config=self.config(volumes={"data": {"name": "scanmylib_data"}}),
        )
        self.assert_refused(
            "secrets (top level)", config=self.config(secrets={"token": {"file": f"{self.prod}/state/token"}})
        )
        self.assert_refused(
            "npipe mount", config=self.service(volumes=[{"type": "npipe", "source": "x", "target": "/x"}])
        )

    def test_production_env_that_breaks_the_format_is_an_error(self) -> None:
        (self.primary / ".env").write_text("DATA_DIR=/data/x # comment\n")
        with self.assertRaisesRegex(stack.EnvError, "production's .env"):
            self.problems()

    def check_paths(self, *args: str) -> tuple[int, str]:
        errors = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("[]")), redirect_stderr(errors):
            return stack.main(["check-paths", *args]), errors.getvalue()

    def test_check_paths_command(self) -> None:
        # build-apk.sh without .env (CI): production's paths and the home directory are refused,
        # except inside GitHub's RUNNER_TEMP, which the runner keeps in its home directory.
        self.assertEqual(self.check_paths(f"DATA_DIR={self.base}/ci", f"ANDROID_DIR={self.base}/ci/a"), (0, ""))
        status, errors = self.check_paths(f"DATA_DIR={self.base}/ci", f"ANDROID_DIR={self.prod}/android")
        self.assertEqual(status, 1)
        self.assertIn(f"ANDROID_DIR: {self.prod}/android is production's ANDROID_DIR", errors)
        status, errors = self.check_paths(f"DATA_DIR={self.home}/ci", f"ANDROID_DIR={self.home}/.config")
        self.assertEqual(status, 1)
        self.assertIn("DATA_DIR: ", errors)
        self.assertIn(f"ANDROID_DIR: {self.home}/.config is inside your home directory", errors)
        runner_temp = f"{self.home}/work/_temp"
        self.assertEqual(
            self.check_paths(
                "--runner-temp", runner_temp, f"DATA_DIR={runner_temp}/ci", f"ANDROID_DIR={runner_temp}/ci/android"
            ),
            (0, ""),
        )
        status, errors = self.check_paths(
            "--runner-temp", runner_temp, f"DATA_DIR={runner_temp}/ci", f"ANDROID_DIR={self.home}/.config"
        )
        self.assertIn(f"ANDROID_DIR: {self.home}/.config is inside your home directory", errors)
        status, errors = self.check_paths("--runner-temp", str(self.home), f"DATA_DIR={self.home}/ci")
        self.assertEqual(status, 1)
        self.assertIn("RUNNER_TEMP: ", errors)


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
