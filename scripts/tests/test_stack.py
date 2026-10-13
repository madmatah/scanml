"""scripts/lib/stack.py: the strict .env format, production's checkout and the isolation of a stack.

Standard library only: python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import stack  # noqa: E402

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


class ReadEnvTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / ".env"

    def tearDown(self):
        self.directory.cleanup()

    def read(self, text: str | bytes) -> dict[str, str]:
        if isinstance(text, str):
            text = text.encode()
        self.path.write_bytes(text)
        return stack.read_env(self.path)

    def test_key_value_lines_comments_and_blank_lines(self):
        values = self.read("# comment\n\nA=1\nPUBLIC_URL=http://192.168.1.10:8765\nEMPTY=\nLAST=a/b_c.d@e%f+g,h-i")
        self.assertEqual(values, {"A": "1", "PUBLIC_URL": "http://192.168.1.10:8765", "EMPTY": "",
                                  "LAST": "a/b_c.d@e%f+g,h-i"})

    def test_lines_docker_compose_would_read_differently_are_refused(self):
        # Each of these makes docker compose resolve COMPOSE_PROJECT_NAME=scanmylib while a naive
        # parser (sed 's/^KEY=//') reads something else.
        for text in [
            "COMPOSE_PROJECT_NAME=scanmylib # dev\n",
            "COMPOSE_PROJECT_NAME=scanmylib \n",
            "COMPOSE_PROJECT_NAME=scanmylib-dev\nexport COMPOSE_PROJECT_NAME=scanmylib\n",
            "COMPOSE_PROJECT_NAME=scanmylib-dev\n  COMPOSE_PROJECT_NAME=scanmylib\n",
            "COMPOSE_PROJECT_NAME=scanmylib-dev\nCOMPOSE_PROJECT_NAME: scanmylib\n",
            "COMPOSE_PROJECT_NAME=scanmylib-dev\nCOMPOSE_PROJECT_NAME = scanmylib\n",
            "X=scanmylib\nCOMPOSE_PROJECT_NAME=${X}\n",
            "X=scanmylib\nCOMPOSE_PROJECT_NAME=$X\n",
            "COMPOSE_PROJECT_NAME=scanmylib\r\n",
            'COMPOSE_PROJECT_NAME="scanmylib" # x\n',
            "COMPOSE_PROJECT_NAME='scanmylib'\n",
            "COMPOSE_PROJECT_NAME=scanmyli\\\nb\n",
            "COMPOSE_PROJECT_NAME=scanmylib-dev\nCOMPOSE_PROJECT_NAME=scanmylib\n",
            "\tCOMPOSE_PROJECT_NAME=scanmylib\n",
            " # an indented comment\n",
            "compose_project_name=scanmylib\n",
            "COMPOSE_PROJECT_NAME\n",
        ]:
            with self.subTest(text=text), self.assertRaises(stack.EnvError):
                self.read(text)

    def test_keys_that_change_what_docker_compose_does_are_refused(self):
        for key in ("COMPOSE_FILE", "COMPOSE_PROFILES", "COMPOSE_ENV_FILES", "COMPOSE_PATH_SEPARATOR",
                    "DOCKER_HOST", "DOCKER_CONTEXT", "BUILDKIT_PROGRESS"):
            with self.subTest(key=key), self.assertRaisesRegex(stack.EnvError, key):
                self.read(f"{key}=x\n")

    def test_errors_name_the_line(self):
        with self.assertRaisesRegex(stack.EnvError, "line 3"):
            self.read("A=1\n# ok\nB=two words\n")

    def test_not_utf8(self):
        with self.assertRaisesRegex(stack.EnvError, "UTF-8"):
            self.read(b"A=\xff\n")

    def test_missing_file(self):
        with self.assertRaises(stack.EnvError):
            stack.read_env(Path(self.directory.name) / "missing")


class ImageTest(unittest.TestCase):
    def test_normalize_image(self):
        for reference, expected in [
            ("scanmylib-api", "docker.io/library/scanmylib-api:latest"),
            ("scanmylib-api:latest", "docker.io/library/scanmylib-api:latest"),
            ("docker.io/scanmylib-api", "docker.io/library/scanmylib-api:latest"),
            ("docker.io/library/scanmylib-api:deployed", "docker.io/library/scanmylib-api:deployed"),
            ("index.docker.io/library/scanmylib-api", "docker.io/library/scanmylib-api:latest"),
            ("someone/scanmylib-api", "docker.io/someone/scanmylib-api:latest"),
            ("localhost/scanmylib-api", "localhost/scanmylib-api:latest"),
            ("registry:5000/scanmylib-api", "registry:5000/scanmylib-api:latest"),
            ("x/y:1@sha256:abc", "docker.io/x/y:1@sha256:abc"),
            ("x@sha256:abc", "docker.io/library/x@sha256:abc"),
        ]:
            with self.subTest(reference=reference):
                self.assertEqual(stack.normalize_image(reference), expected)

    def test_repository(self):
        self.assertEqual(stack.repository("scanmylib-api:latest"), "docker.io/library/scanmylib-api")
        self.assertEqual(stack.repository("index.docker.io/library/scanmylib-api"), "docker.io/library/scanmylib-api")
        self.assertEqual(stack.repository("registry:5000/scanmylib-api"), "registry:5000/scanmylib-api")
        self.assertEqual(stack.repository("x/y:1@sha256:abc"), "docker.io/x/y")


def fake_home(test: unittest.TestCase, home: Path) -> None:
    """Makes `home` the user's home directory, in the password database and in $HOME."""
    for patcher in (mock.patch.dict(os.environ, {"HOME": str(home)}),
                    mock.patch.object(stack, "user_home", return_value=str(home))):
        patcher.start()
        test.addCleanup(patcher.stop)


class ProductionCheckoutTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.home = Path(os.path.realpath(directory.name))
        fake_home(self, self.home)

    @staticmethod
    def container(working_dir: str) -> dict:
        return {"Name": "/scanmylib-api-1", "Config": {"Labels": {stack.WORKING_DIR_LABEL: working_dir}}}

    def test_the_project_directory_of_production_s_containers(self):
        checkout = self.home / "elsewhere"
        self.assertEqual(stack.production_checkout([self.container(str(checkout)), self.container(str(checkout))]),
                         checkout)

    def test_without_containers_the_default(self):
        self.assertEqual(stack.production_checkout([]), self.home / "Dev" / "scanmylib")

    def test_the_home_directory_comes_from_the_password_database(self):
        # $HOME pointing elsewhere moves neither production's checkout nor the home barrier.
        with mock.patch.dict(os.environ, {"HOME": "/elsewhere"}):
            self.assertEqual(stack.production_checkout([]), self.home / "Dev" / "scanmylib")
            self.assertEqual(stack.homes(), {str(self.home), "/elsewhere"})

    def test_containers_from_several_checkouts_are_an_error(self):
        with self.assertRaisesRegex(stack.EnvError, "several checkouts"):
            stack.production_checkout([self.container("/a"), self.container("/b")])

    def test_command_line(self):
        output = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps([self.container(f"{self.home}/prod")]))), \
                mock.patch("sys.stdout", output):
            self.assertEqual(stack.main(["production-checkout"]), 0)
        self.assertEqual(output.getvalue().strip(), f"{self.home}/prod")


class IsolationTest(unittest.TestCase):
    """isolation_problems() on configurations shaped like `docker compose config --format json`."""

    def setUp(self):
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
        self.env = dict(line.split("=", 1) for line in DEV_ENV.format(dev=self.dev, prod=self.prod).splitlines()
                        if line and not line.startswith("#"))

    def config(self, **changes) -> dict:
        dev, prod, worktree = self.dev, self.prod, self.worktree
        created = {"create_host_path": True}
        config = {
            "name": "scanmylib-dev",
            "networks": {"default": {"name": "scanmylib-dev_default", "ipam": {}}},
            "x-ocr-env": {"HOME": "/tmp/home"},
            "services": {
                "api": {
                    "build": {"context": f"{worktree}/server", "dockerfile": "Dockerfile", "target": "runtime",
                              "args": {"UID": "1000"}, "additional_contexts": {"project": str(worktree)}},
                    "image": "scanmylib-dev-api:latest",
                    "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"], "read_only": True,
                    "ports": [{"target": 8765, "published": "8770"}],
                    "tmpfs": ["/tmp:size=512m,mode=1777"],
                    "networks": {"default": None},
                    "volumes": [
                        {"type": "bind", "source": f"{dev}/library", "target": "/library", "bind": created},
                        {"type": "bind", "source": f"{dev}/state", "target": "/state", "bind": created},
                        {"type": "bind", "source": f"{dev}/run", "target": "/run/scanmylib", "bind": created},
                        {"type": "bind", "source": f"{dev}/app", "target": "/app-dist", "read_only": True,
                         "bind": created},
                    ],
                },
                "ocr": {
                    "build": {"context": f"{worktree}/ocr", "dockerfile": "Dockerfile"},
                    "image": "scanmylib-dev-ocr:latest",
                    "network_mode": "none",
                    "devices": [{"source": "nvidia.com/gpu=all", "target": "nvidia.com/gpu=all", "permissions": "rwm"}],
                    "volumes": [
                        {"type": "bind", "source": f"{prod}/sandbox", "target": "/opt/sandbox", "read_only": True,
                         "bind": created},
                        {"type": "bind", "source": f"{dev}/run", "target": "/run/scanmylib", "bind": created},
                        {"type": "bind", "source": f"{dev}/ocr-cache", "target": "/var/cache/ocr", "bind": created},
                    ],
                },
                "ocr-fake": {"image": "scanmylib-dev-api:latest", "pull_policy": "never", "profiles": ["fake-ocr"],
                             "network_mode": "none"},
                "ocr-setup": {
                    "build": {"context": f"{worktree}/ocr", "dockerfile": "Dockerfile"},
                    "image": "scanmylib-dev-ocr:latest",
                    "volumes": [{"type": "bind", "source": "/nonexistent/SANDBOX_SETUP_DIR", "target": "/opt/sandbox",
                                 "bind": {}}],
                },
            },
        }
        config.update(changes)
        return config

    def problems(self, config=None, env=None, containers=(), raw=None, compose_file=None) -> list[str]:
        checkout = stack.production_checkout(list(containers))
        production = stack.production_identity(checkout, list(containers))
        config = config or self.config()
        return stack.isolation_problems(env or self.env, config, raw or config, production, str(self.worktree),
                                        compose_file)

    def assertRefused(self, pattern: str, **kwargs):
        problems = self.problems(**kwargs)
        self.assertTrue(any(pattern in problem for problem in problems), problems)

    def service(self, name: str = "api", **settings) -> dict:
        config = self.config()
        config["services"][name].update(settings)
        return config

    def test_the_development_stack_shares_nothing(self):
        self.assertEqual(self.problems(), [])

    def test_production_project_images_and_ports(self):
        self.assertRefused("the project is production's", config=self.config(name="scanmylib"))
        self.assertRefused("the image scanmylib-api:dev is production's", config=self.service(image="scanmylib-api:dev"))
        self.assertRefused("publishes port 8765", config=self.service(ports=[{"target": 8765, "published": "8760-8770"}]))

    def test_image_names_as_docker_reads_them(self):
        for image in ("docker.io/library/scanmylib-api:latest", "docker.io/scanmylib-api",
                      "index.docker.io/library/scanmylib-api:latest"):
            with self.subTest(image=image):
                self.assertRefused(f"the image {image} is production's", config=self.service(image=image))
        for image in ("scanmylib-dev-api:dev", "scanmylib-dev-other:latest", "docker.io/library/scanmylib-dev-api:latest",
                      "busybox:latest"):
            with self.subTest(image=image):
                self.assertRefused("is not one of the stack's own", config=self.service(image=image))
        for prefix in ("docker.io/library/scanmylib", "docker.io/scanmylib", "index.docker.io/library/scanmylib",
                       "Scanmylib-dev", "scanmylib.dev"):
            with self.subTest(prefix=prefix):
                self.assertRefused("may only contain lowercase letters", env={**self.env, "IMAGE_PREFIX": prefix})

    def bind(self, source: str, read_only: bool = False, service: str = "api", create: bool = True) -> dict:
        config = self.config()
        config["services"][service]["volumes"].append(
            {"type": "bind", "source": source, "target": "/x", "read_only": read_only,
             "bind": {"create_host_path": True} if create else {}})
        return config

    def test_host_paths_of_production(self):
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
                self.assertRefused(expected, config=self.bind(source))

    def test_home_from_the_password_database_and_home_variable(self):
        # $HOME points elsewhere: both home directories are refused.
        elsewhere = self.base / "elsewhere-home"
        with mock.patch.dict(os.environ, {"HOME": str(elsewhere)}):
            for data_dir in (f"{self.home}/dev", f"{elsewhere}/dev"):
                with self.subTest(data_dir=data_dir):
                    self.assertRefused("is inside your home directory", env={**self.env, "DATA_DIR": data_dir})

    def test_every_other_path_is_inside_the_stack_s_data_dir(self):
        self.assertRefused("is not inside the stack's DATA_DIR", config=self.bind(f"{self.base}/elsewhere"))
        self.assertRefused("is not inside the stack's DATA_DIR",
                           config=self.bind(f"{self.base}/elsewhere", read_only=True))
        for key, value in [("LIBRARY_DIR", "/tmp"), ("LIBRARY_DIR", f"{self.base}/library2"),
                           ("ANDROID_DIR", f"{self.base}/android"), ("SANDBOX_SETUP_DIR", f"{self.base}/sandbox"),
                           ("SANDBOX_DIR", "/tmp"), ("ANDROID_KEYSTORE_DIR", f"{self.base}/keys"),
                           ("LIBRARY_DIR", f"{self.home}/.ssh")]:
            with self.subTest(key=key, value=value):
                self.assertRefused(f"{key} in .env", env={**self.env, key: value})
        for value, expected in [("/tmp", "is or contains /tmp"), ("/var/tmp/dev", "system directory"),
                                (f"{self.home}/scanmylib-dev", "is inside your home directory"),
                                ("relative/dev", "not an absolute path")]:
            with self.subTest(data_dir=value):
                self.assertRefused(expected, env={**self.env, "DATA_DIR": value})
        self.assertRefused("no DATA_DIR in .env", env={key: value for key, value in self.env.items() if key != "DATA_DIR"})

    def test_production_sandbox_is_shared_read_only_only(self):
        self.assertEqual(self.problems(config=self.bind(f"{self.prod}/sandbox/models", read_only=True)), [])
        self.assertRefused("is production's DATA_DIR", config=self.bind(str(self.prod), read_only=True))
        self.assertRefused("contains production's SANDBOX_DIR", config=self.bind(str(self.prod), read_only=True))

    def test_a_bind_mount_docker_would_never_create(self):
        # The placeholder of ocr-setup: no such path, and docker compose does not create it.
        self.assertEqual(self.problems(config=self.bind("/nonexistent/x", create=False)), [])
        self.assertRefused("is not inside the stack's DATA_DIR", config=self.bind(f"{self.base}/missing", create=True))
        # A path this user cannot see may exist for the Docker daemon.
        if os.getuid() != 0 and not os.access("/root", os.X_OK):
            self.assertRefused("system directory", config=self.bind("/root/.ssh", create=False))

    def test_paths_from_the_running_production_containers(self):
        elsewhere = self.dev / "moved-library"
        container = {
            "Name": "/scanmylib-api-1",
            "Config": {"Image": "scanmylib-api:latest", "Labels": {"com.docker.compose.project": "scanmylib",
                                                                  stack.WORKING_DIR_LABEL: str(self.primary)}},
            "Mounts": [{"Type": "bind", "Source": str(elsewhere), "Destination": "/library"}],
            "HostConfig": {"PortBindings": {"8765/tcp": [{"HostIp": "", "HostPort": "9999"}]}},
        }
        self.assertRefused("mount /library of scanmylib-api-1", config=self.bind(str(elsewhere)), containers=[container])
        self.assertRefused("publishes port 9999", config=self.service(ports=[{"target": 8765, "published": "9999"}]),
                           containers=[container])

    def test_production_checkout_from_its_containers(self):
        # Production runs from another checkout: that one is production's, whatever ~/Dev holds.
        moved = self.base / "moved-checkout"
        moved.mkdir()
        (moved / ".env").write_text(f"COMPOSE_PROJECT_NAME=scanmylib\nDATA_DIR={self.base}/moved-data\n")
        container = {"Name": "/scanmylib-api-1", "Config": {"Labels": {stack.WORKING_DIR_LABEL: str(moved)}}}
        self.assertRefused("is production's checkout", config=self.bind(str(moved)), containers=[container])
        self.assertRefused("is production's DATA_DIR", env={**self.env, "DATA_DIR": f"{self.base}/moved-data"},
                           containers=[container])

    def test_paths_the_scripts_use(self):
        for key, value, expected in [
            ("DATA_DIR", str(self.prod), "DATA_DIR in .env"),
            ("ANDROID_DIR", f"{self.prod}/android", "ANDROID_DIR in .env"),
            ("SANDBOX_SETUP_DIR", f"{self.prod}/sandbox", "SANDBOX_SETUP_DIR in .env"),
            ("ANDROID_KEYSTORE_DIR", str(self.prod / "android"), "ANDROID_KEYSTORE_DIR in .env"),
            ("SANDBOX_DIR", str(self.prod), "SANDBOX_DIR in .env"),
            ("LIBRARY_DIR", "relative/library", "not an absolute path"),
        ]:
            with self.subTest(key=key):
                self.assertRefused(expected, env={**self.env, key: value})

    def test_variants_and_services(self):
        self.assertRefused("only production builds the release app", env={**self.env, "APP_VARIANT": "release"})
        self.assertRefused("expected ocr or ocr-fake", env={**self.env, "OCR_SERVICE": "other"})
        self.assertRefused(".env says 'scanmylib-dev2'", env={**self.env, "COMPOSE_PROJECT_NAME": "scanmylib-dev2"})

    def test_settings_outside_the_allowlist(self):
        for settings, expected in [
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
        ]:
            with self.subTest(settings=settings):
                self.assertRefused(expected, config=self.service(**settings))

    def test_network_mode_of_the_stack(self):
        for network_mode in ("none", "service:ocr"):
            with self.subTest(network_mode=network_mode):
                self.assertEqual(self.problems(config=self.service(network_mode=network_mode)), [])

    def test_settings_that_only_the_configuration_without_interpolation_shows(self):
        # docker compose config merges env_file into environment: only the raw configuration
        # (--no-interpolate) still has it.
        raw = self.config()
        raw["services"]["api"]["env_file"] = [{"path": f"{self.home}/.aws/credentials", "required": True}]
        self.assertRefused("service api: env_file is not allowed", raw=raw)
        self.assertRefused("no configuration without interpolation", raw={"services": {}})

    def test_include_in_the_compose_file(self):
        compose = self.base / "compose.yaml"
        for text in ("include:\n  - path: x.yaml\n    env_file: /home/x/.env\n", '{"include": ["x.yaml"]}',
                     "name: x\n'include' :\n  - x.yaml\n"):
            with self.subTest(text=text):
                compose.write_text(text)
                self.assertRefused("include is not allowed", compose_file=str(compose))
        compose.write_text("# include: a comment\nservices:\n  api:\n    command: [sh, -c, 'echo include']\n")
        self.assertEqual(self.problems(compose_file=str(compose)), [])

    def test_build_settings(self):
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
                self.assertRefused(expected, config=self.service(build=build))

    def test_networks_volumes_and_top_level_settings(self):
        self.assertRefused("network default", config=self.config(networks={"default": {"name": "scanmylib_default"}}))
        self.assertRefused("network default", config=self.config(
            networks={"default": {"name": "scanmylib-dev_default", "external": True}}))
        self.assertRefused("driver and driver_opts", config=self.config(volumes={"data": {
            "name": "scanmylib-dev_data", "driver_opts": {"type": "none", "o": "bind", "device": str(self.home)}}}))
        for network in ({"driver": "macvlan", "driver_opts": {"parent": "eth0"}}, {"driver": "ipvlan"}):
            with self.subTest(network=network):
                self.assertRefused("network default: driver and driver_opts", config=self.config(
                    networks={"default": {"name": "scanmylib-dev_default", **network}}))
        self.assertRefused("volume data (scanmylib_data) is not the stack's own",
                           config=self.config(volumes={"data": {"name": "scanmylib_data"}}))
        self.assertRefused("secrets (top level)", config=self.config(secrets={"token": {"file": f"{self.prod}/state/token"}}))
        self.assertRefused("npipe mount", config=self.service(volumes=[{"type": "npipe", "source": "x", "target": "/x"}]))

    def test_production_env_that_breaks_the_format_is_an_error(self):
        (self.primary / ".env").write_text("DATA_DIR=/data/x # comment\n")
        with self.assertRaisesRegex(stack.EnvError, "production's .env"):
            self.problems()

    def check_paths(self, *args: str) -> tuple[int, str]:
        errors = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("[]")), redirect_stderr(errors):
            return stack.main(["check-paths", *args]), errors.getvalue()

    def test_check_paths_command(self):
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
        self.assertEqual(self.check_paths("--runner-temp", runner_temp, f"DATA_DIR={runner_temp}/ci",
                                          f"ANDROID_DIR={runner_temp}/ci/android"), (0, ""))
        status, errors = self.check_paths("--runner-temp", runner_temp, f"DATA_DIR={runner_temp}/ci",
                                          f"ANDROID_DIR={self.home}/.config")
        self.assertIn(f"ANDROID_DIR: {self.home}/.config is inside your home directory", errors)
        status, errors = self.check_paths("--runner-temp", str(self.home), f"DATA_DIR={self.home}/ci")
        self.assertEqual(status, 1)
        self.assertIn("RUNNER_TEMP: ", errors)


class ComposeCommandTest(unittest.TestCase):
    @staticmethod
    def refused(*argv: str, production: bool = False) -> list[str]:
        return stack.compose_command_problems(list(argv), production=production)

    def test_allowed(self):
        for argv in (["ps"], ["up", "-d", "api"], ["exec", "api", "sh"], ["exec", "-T", "-u", "1000", "api", "id"],
                     ["run", "--rm", "-e", "X=1", "api", "pytest", "-v", "-p", "no:cacheprovider"],
                     ["run", "-dT", "--entrypoint=sh", "api"], ["run", "-eX=1", "--rm", "api"],
                     ["build", "--no-cache", "api"], ["build", "api", "--no-cache"], ["logs", "-f", "api"],
                     ["down", "-v"], ["config"], ["config", "--format", "json", "--no-interpolate"],
                     ["config", "--hash", "api"], ["up", "-d", "--wait", "--wait-timeout", "60", "api", "ocr-fake"],
                     ["up", "api", "-d", "--timeout", "5"], ["restart", "-t", "5", "api"], ["start", "ocr"],
                     ["create", "--no-build", "--", "api"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.refused(*argv), [])

    def test_global_options_and_commands_outside_the_stack(self):
        for argv in (["-p", "scanmylib", "down"], ["--project-name=scanmylib", "down"], ["--file", "x.yaml", "ps"], []):
            with self.subTest(argv=argv):
                self.assertIn("no global option", self.refused(*argv)[0])
        for command in ("cp", "export", "commit", "push", "pull", "publish", "watch", "bridge", "scale"):
            with self.subTest(command=command):
                self.assertIn(f"docker compose {command} is not allowed", self.refused(command, "api")[0])

    def test_options_that_give_a_container_more(self):
        for argv, expected in [
            (["run", "-v", "/:/host", "api"], "run -v"),
            (["run", "--volume=/home:/h", "api"], "run --volume"),
            (["run", "-dv", "/:/host", "api"], "run -v"),
            (["run", "-p", "8765:8765", "api"], "run -p"),
            (["run", "--publish", "8765:8765", "api"], "run --publish"),
            (["run", "--cap-add", "SYS_ADMIN", "api"], "run --cap-add"),
            (["run", "--env-from-file", "/home/x/.env", "api"], "run --env-from-file"),
            (["run", "-l", "com.docker.compose.project=scanmylib", "api"], "run -l"),
            (["run", "--name", "scanmylib-api-1", "api"], "run --name"),
            (["run", "--rm", "-e", "X", "-v", "/:/h", "api"], "run -v"),
            (["exec", "--privileged", "api", "sh"], "exec --privileged"),
            (["build", "--ssh", "default", "api"], "build --ssh"),
            (["build", "--push"], "build --push"),
            # Options after the service names: docker compose reads them as options too.
            (["build", "api", "--ssh", "default=/home/x/.ssh/id_ed25519"], "build --ssh"),
            (["build", "api", "--push"], "build --push"),
            (["build", "api", "ocr", "-q", "--push"], "build --push"),
            (["config", "-o", "/home/x/Dev/scanmylib/.env"], "config -o"),
            (["config", "--output=/home/x/.bashrc"], "config --output"),
            (["config", "--format", "json", "--output", "x"], "config --output"),
            (["up", "-d", "api", "--watch"], "up --watch"),
            (["up", "-dw", "api"], "up -w"),
            # --scale starts the services it names, listed or not.
            (["up", "-d", "api", "ocr", "--scale", "ocr-fake=1"], "up --scale"),
            (["create", "--scale=ocr-fake=1", "api"], "create --scale"),
        ]:
            with self.subTest(argv=argv):
                problems = self.refused(*argv)
                self.assertTrue(problems and expected in problems[0], problems)

    def test_both_ocr_services_never_start_together(self):
        for argv in (["up", "-d"], ["up", "-d", "--wait"], ["restart"], ["start"], ["create", "--", ]):
            with self.subTest(argv=argv):
                problems = self.refused(*argv)
                self.assertTrue(problems and "name them" in problems[0], problems)
        for argv in (["up", "-d", "api", "ocr", "ocr-fake"], ["start", "ocr-fake", "ocr"], ["up", "ocr", "--", "ocr-fake"]):
            with self.subTest(argv=argv):
                problems = self.refused(*argv)
                self.assertTrue(problems and "never start both" in problems[0], problems)

    def test_production(self):
        for argv in (["ps"], ["logs", "-f", "api", "ocr"], ["restart", "api"], ["up", "-d", "--no-build", "api", "ocr"],
                     ["up", "-d"], ["restart"], ["stop", "api", "ocr"], ["down"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.refused(*argv, production=True), [])
        for argv, expected in [(["build", "api"], "scripts/deploy.sh"), (["run", "api", "sh"], "scripts/deploy.sh"),
                               (["up", "-d", "--build"], "--build"), (["exec", "--privileged", "api", "sh"], "--privileged"),
                               (["cp", "api:/state/token", "."], "not allowed"), (["up", "-d", "ocr-fake"], "fake OCR"),
                               (["config", "-o", ".env"], "config -o")]:
            with self.subTest(argv=argv):
                problems = self.refused(*argv, production=True)
                self.assertTrue(problems and expected in problems[0], problems)


if __name__ == "__main__":
    unittest.main()
