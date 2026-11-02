"""The sandbox's images (ocr/Dockerfile, compose.yaml): which one holds uv and pip, and which service runs each.

Standard library only:
    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import re
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGE_PATTERN = re.compile(r"^FROM (?P<parent>\S+)(?: AS (?P<name>\S+))?$")
ANCHOR_PATTERN = re.compile(r"^(?P<name>\S+): &(?P<anchor>\S+)$", re.MULTILINE)
UNINSTALL_PIP = "python3 -m pip uninstall --yes pip"
REMOVE_PIP_WHEEL = "rm /usr/local/lib/python3.12/ensurepip/_bundled/pip-*.whl"


@dataclass(frozen=True)
class Stage:
    name: str
    parent: str
    instructions: tuple[str, ...]


def read_stages(dockerfile_text: str) -> dict[str, Stage]:
    joined_text = re.sub(r"\\\n\s*", " ", dockerfile_text)
    stages: dict[str, Stage] = {}
    name, parent = "", ""
    instructions: list[str] = []
    for line in joined_text.splitlines():
        stage_start = STAGE_PATTERN.match(line)
        if stage_start is not None:
            if name:
                stages[name] = Stage(name, parent, tuple(instructions))
            name, parent, instructions = stage_start["name"] or "", stage_start["parent"], []
        elif line.strip() and not line.lstrip().startswith("#"):
            instructions.append(line.strip())
    if name:
        stages[name] = Stage(name, parent, tuple(instructions))
    return stages


def _measure_indentation(line: str) -> int:
    return len(line) - len(line.lstrip())


def read_block(lines: list[str], header: str) -> list[str]:
    start = lines.index(header)
    block = []
    for line in lines[start + 1 :]:
        if line.strip() and _measure_indentation(line) <= _measure_indentation(header):
            break
        block.append(line)
    return block


def find_build_target(compose_text: str, service: str) -> str:
    lines = compose_text.splitlines()
    anchors = {match["anchor"]: match["name"] for match in ANCHOR_PATTERN.finditer(compose_text)}
    service_block = read_block(lines, f"  {service}:")
    build_line = next(line for line in service_block if line.strip().startswith("build:"))
    build_block = read_block(service_block, build_line)
    alias = re.fullmatch(r"\s*build: \*(\S+)", build_line)
    merged_alias = next((match[1] for line in build_block if (match := re.fullmatch(r"\s*<<: \*(\S+)", line))), None)
    targets = [match[1] for line in build_block if (match := re.fullmatch(r"\s*target: (\S+)", line))]
    if not targets:
        anchor = alias[1] if alias is not None else merged_alias
        anchor_block = read_block(lines, f"{anchors[anchor]}: &{anchor}") if anchor is not None else []
        targets = [match[1] for line in anchor_block if (match := re.fullmatch(r"\s*target: (\S+)", line))]
    return targets[0] if targets else ""


class TheDockerfile(unittest.TestCase):
    def setUp(self) -> None:
        self.stages = read_stages((ROOT / "ocr" / "Dockerfile").read_text())
        self.stages_installing_uv = [
            stage.name for stage in self.stages.values() if any("uv==" in line for line in stage.instructions)
        ]
        runtime = self.stages["runtime"]
        self.runtime_parent = runtime.parent
        self.runtime_runs = [line for line in runtime.instructions if line.startswith("RUN ")]

    def test_should_install_uv_only_in_the_setup_image_so_that_the_image_the_sandbox_runs_holds_no_installer(
        self,
    ) -> None:
        self.assertEqual(self.stages_installing_uv, ["setup"])

    def test_should_build_the_runtime_image_on_the_base_alone_so_that_it_inherits_nothing_of_the_setup_image(
        self,
    ) -> None:
        self.assertEqual(self.runtime_parent, "base")

    def test_should_uninstall_pip_from_the_runtime_image(self) -> None:
        self.assertTrue(any(UNINSTALL_PIP in line for line in self.runtime_runs), self.runtime_runs)

    def test_should_remove_the_wheel_of_pip_that_ensurepip_keeps_from_the_runtime_image(self) -> None:
        self.assertTrue(any(REMOVE_PIP_WHEEL in line for line in self.runtime_runs), self.runtime_runs)


class TheComposeFile(unittest.TestCase):
    def setUp(self) -> None:
        compose_text = (ROOT / "compose.yaml").read_text()
        self.ocr_target = find_build_target(compose_text, "ocr")
        self.ocr_setup_target = find_build_target(compose_text, "ocr-setup")

    def test_should_build_the_ocr_service_from_the_runtime_image(self) -> None:
        self.assertEqual(self.ocr_target, "runtime")

    def test_should_build_the_ocr_setup_service_from_the_setup_image(self) -> None:
        self.assertEqual(self.ocr_setup_target, "setup")


if __name__ == "__main__":
    unittest.main()
