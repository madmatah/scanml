"""The layers of the api: what the modules of each layer import and call, read from their source."""

from __future__ import annotations

import ast
import importlib.util
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType

import pytest

PACKAGE_DIRECTORY = Path(__file__).resolve().parent.parent / "scanmylib"
PACKAGE_NAME = "scanmylib"
#: The web UI that the api serves, which holds none of the api's Python.
WEB_UI_DIRECTORY = "web"


class Layer(Enum):
    DOMAIN = "domain"
    APPLICATION = "application"
    ADAPTERS = "adapters"
    COMPOSITION_ROOT = "composition root"
    TEST_SUPPORT = "test support"
    NOT_RESTRUCTURED = "not restructured"


LAYER_DIRECTORIES = MappingProxyType(
    {
        "domain": Layer.DOMAIN,
        "application": Layer.APPLICATION,
        "adapters": Layer.ADAPTERS,
        "devtools": Layer.TEST_SUPPORT,
    }
)
COMPOSITION_ROOTS = frozenset(
    {PACKAGE_NAME, f"{PACKAGE_NAME}.__main__", f"{PACKAGE_NAME}.app", f"{PACKAGE_NAME}.config"}
)
LAYERS = frozenset({Layer.DOMAIN, Layer.APPLICATION, Layer.ADAPTERS})
INNER_LAYERS_OF_THE_APPLICATION = frozenset({Layer.DOMAIN, Layer.APPLICATION})
OUTER_LAYERS_OF_THE_ADAPTERS = frozenset({Layer.COMPOSITION_ROOT, Layer.TEST_SUPPORT})
#: The libraries of plain values that do no I/O and read no clock, which .claude/rules/architecture.md > Layers lets the
#: domain use.
DOMAIN_ALLOWLIST = frozenset(
    {
        "__future__",
        "bisect",
        "collections",
        "collections.abc",
        "dataclasses",
        "datetime",
        "enum",
        "itertools",
        "json",
        "math",
        "re",
        "typing",
        "unicodedata",
    }
)
#: What the application may import besides the inner layers: the libraries of plain values (contextlib, hashlib, hmac);
#: Python's runtime, which .claude/rules/architecture.md > Ports and wiring lets the api's application use without a
#: port (asyncio, logging, and secrets, which no test replaces); and a location that cannot open its file
#: (pathlib.PurePath, .claude/rules/python.md, "Plain data is a frozen dataclass").
APPLICATION_ALLOWLIST = DOMAIN_ALLOWLIST | frozenset(
    {"asyncio", "contextlib", "hashlib", "hmac", "logging", "secrets", "pathlib.PurePath"}
)
#: pathlib holds both PurePath, which the application may import, and Path, which it may not, so its names are checked
#: one by one.
MODULES_CHECKED_BY_NAME = frozenset({"pathlib"})
WALL_CLOCK_CLASSES = frozenset({"datetime", "date"})
WALL_CLOCK_ATTRIBUTES = frozenset({"now", "today", "utcnow"})
BUILTIN_INPUT_OUTPUT_FUNCTIONS = frozenset({"open", "print", "input", "exec", "eval", "compile", "__import__"})
ASYNCIO_INPUT_OUTPUT_FUNCTIONS = frozenset(
    {
        "open_connection",
        "open_unix_connection",
        "start_server",
        "start_unix_server",
        "create_subprocess_exec",
        "create_subprocess_shell",
        "create_connection",
        "create_datagram_endpoint",
        "create_server",
        "create_unix_connection",
        "create_unix_server",
        "connect_accepted_socket",
        "connect_read_pipe",
        "connect_write_pipe",
        "subprocess_exec",
        "subprocess_shell",
        "sock_accept",
        "sock_connect",
        "sock_recv",
        "sock_recv_into",
        "sock_recvfrom",
        "sock_recvfrom_into",
        "sock_sendall",
        "sock_sendfile",
        "sock_sendto",
        "getaddrinfo",
        "getnameinfo",
        "start_tls",
        "sendfile",
        "add_reader",
        "add_writer",
    }
)


@dataclass(frozen=True)
class SourceModule:
    name: str
    is_package: bool
    tree: ast.Module


@dataclass(frozen=True)
class LayerFindings:
    imports_outside_the_domain: list[str]
    wall_clock_reads: list[str]
    input_output_calls: list[str]
    imports_outside_the_application: list[str]
    application_wall_clock_reads: list[str]
    application_input_output_calls: list[str]
    outer_imports_of_the_adapters: list[str]
    imports_of_unrestructured_modules: list[str]
    modules_on_an_import_cycle: list[str]
    domain_module_count: int
    application_module_count: int
    adapter_module_count: int
    layered_module_count: int
    package_module_count: int


@dataclass(frozen=True)
class PackageLayers:
    findings: LayerFindings
    domain_file_count: int
    application_file_count: int
    adapter_file_count: int
    layered_file_count: int
    package_file_count: int


@dataclass(frozen=True)
class ImportForm:
    description: str
    module_name: str
    is_package: bool
    source: str
    imported_modules: tuple[str, ...]


def read_package(directory: Path) -> dict[str, SourceModule]:
    sources: dict[str, tuple[bool, str]] = {}
    for path in sorted(directory.rglob("*.py")):
        parts = path.relative_to(directory.parent).with_suffix("").parts
        if parts[1] == WEB_UI_DIRECTORY:
            continue
        is_package = parts[-1] == "__init__"
        sources[".".join(parts[:-1] if is_package else parts)] = (is_package, path.read_text(encoding="utf-8"))
    return parse_package(sources)


def parse_package(sources: Mapping[str, tuple[bool, str]]) -> dict[str, SourceModule]:
    return {
        name: SourceModule(name, is_package, ast.parse(source, filename=name))
        for name, (is_package, source) in sources.items()
    }


def count_python_files(directory: Path) -> int:
    return sum(1 for _ in directory.rglob("*.py"))


def find_layer(module_name: str) -> Layer:
    if module_name in COMPOSITION_ROOTS:
        return Layer.COMPOSITION_ROOT
    return LAYER_DIRECTORIES.get(module_name.split(".")[1], Layer.NOT_RESTRUCTURED)


def walk_in_source_order(tree: ast.Module) -> list[ast.stmt | ast.expr]:
    nodes = [node for node in ast.walk(tree) if isinstance(node, ast.stmt | ast.expr)]
    return sorted(nodes, key=lambda node: (node.lineno, node.col_offset))


def resolve_import_base(statement: ast.ImportFrom, module: SourceModule) -> str:
    relative_name = "." * statement.level + (statement.module or "")
    if statement.level == 0:
        return relative_name
    package = module.name if module.is_package else module.name.rpartition(".")[0]
    return importlib.util.resolve_name(relative_name, package)


def resolve_import(
    statement: ast.Import | ast.ImportFrom, module: SourceModule, package_modules: Collection[str]
) -> list[str]:
    if isinstance(statement, ast.Import):
        return [alias.name for alias in statement.names]
    base = resolve_import_base(statement, module)
    submodules = (f"{base}.{alias.name}" for alias in statement.names)
    return [submodule if submodule in package_modules else base for submodule in submodules]


def list_imported_modules(module: SourceModule, package_modules: Collection[str]) -> list[str]:
    statements = [node for node in walk_in_source_order(module.tree) if isinstance(node, ast.Import | ast.ImportFrom)]
    imported_modules = (name for statement in statements for name in resolve_import(statement, module, package_modules))
    return list(dict.fromkeys(imported_modules))


def resolve_import_by_name(
    statement: ast.Import | ast.ImportFrom, module: SourceModule, package_modules: Collection[str]
) -> list[str]:
    if isinstance(statement, ast.ImportFrom) and statement.level == 0 and statement.module in MODULES_CHECKED_BY_NAME:
        return [f"{statement.module}.{alias.name}" for alias in statement.names]
    return resolve_import(statement, module, package_modules)


def list_imported_names(module: SourceModule, package_modules: Collection[str]) -> list[str]:
    statements = [node for node in walk_in_source_order(module.tree) if isinstance(node, ast.Import | ast.ImportFrom)]
    imported_names = (
        name for statement in statements for name in resolve_import_by_name(statement, module, package_modules)
    )
    return list(dict.fromkeys(imported_names))


def select_modules(package: Mapping[str, SourceModule], layers: Collection[Layer]) -> list[SourceModule]:
    return [package[name] for name in sorted(package) if find_layer(name) in layers]


def list_package_imports(module: SourceModule, package: Mapping[str, SourceModule]) -> list[str]:
    return [imported for imported in list_imported_modules(module, package.keys()) if imported in package]


def is_allowed_in_the_domain(imported: str, package: Mapping[str, SourceModule]) -> bool:
    return imported in DOMAIN_ALLOWLIST or (imported in package and find_layer(imported) is Layer.DOMAIN)


def find_imports_outside_the_domain(package: Mapping[str, SourceModule]) -> list[str]:
    return [
        f"{module.name} imports {imported}"
        for module in select_modules(package, {Layer.DOMAIN})
        for imported in list_imported_modules(module, package.keys())
        if not is_allowed_in_the_domain(imported, package)
    ]


def is_allowed_in_the_application(imported: str, package: Mapping[str, SourceModule]) -> bool:
    return imported in APPLICATION_ALLOWLIST or (
        imported in package and find_layer(imported) in INNER_LAYERS_OF_THE_APPLICATION
    )


def find_imports_outside_the_application(package: Mapping[str, SourceModule]) -> list[str]:
    return [
        f"{module.name} imports {imported}"
        for module in select_modules(package, {Layer.APPLICATION})
        for imported in list_imported_names(module, package.keys())
        if not is_allowed_in_the_application(imported, package)
    ]


def find_wall_clock_reads(package: Mapping[str, SourceModule]) -> list[str]:
    return [
        f"{module.name} reads {node.attr}"
        for module in select_modules(package, {Layer.DOMAIN})
        for node in walk_in_source_order(module.tree)
        if isinstance(node, ast.Attribute) and node.attr in WALL_CLOCK_ATTRIBUTES
    ]


def list_wall_clock_class_names(module: SourceModule) -> frozenset[str]:
    aliases = (
        alias.asname or alias.name
        for node in walk_in_source_order(module.tree)
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "datetime"
        for alias in node.names
        if alias.name in WALL_CLOCK_CLASSES
    )
    return WALL_CLOCK_CLASSES | frozenset(aliases)


def name_wall_clock_read_through_its_class(node: ast.stmt | ast.expr, class_names: Collection[str]) -> str | None:
    match node:
        case ast.Attribute(value=ast.Name(id=class_name), attr=attribute) if (
            class_name in class_names and attribute in WALL_CLOCK_ATTRIBUTES
        ):
            return f"{class_name}.{attribute}"
        case ast.Attribute(value=ast.Attribute(attr=class_name), attr=attribute) if (
            class_name in WALL_CLOCK_CLASSES and attribute in WALL_CLOCK_ATTRIBUTES
        ):
            return f"{class_name}.{attribute}"
    return None


def find_wall_clock_reads_through_their_classes(package: Mapping[str, SourceModule]) -> list[str]:
    reads: list[str] = []
    for module in select_modules(package, {Layer.APPLICATION}):
        class_names = list_wall_clock_class_names(module)
        reads.extend(
            f"{module.name} reads {read}"
            for node in walk_in_source_order(module.tree)
            if (read := name_wall_clock_read_through_its_class(node, class_names)) is not None
        )
    return reads


def name_input_output_function(call: ast.Call) -> str | None:
    match call.func:
        case ast.Name(id=name) if name in BUILTIN_INPUT_OUTPUT_FUNCTIONS | ASYNCIO_INPUT_OUTPUT_FUNCTIONS:
            return name
        case ast.Attribute(attr=name) if name in ASYNCIO_INPUT_OUTPUT_FUNCTIONS:
            return name
    arguments = [*call.args, *(keyword.value for keyword in call.keywords)]
    passed_functions = (
        argument.id
        for argument in arguments
        if isinstance(argument, ast.Name) and argument.id in BUILTIN_INPUT_OUTPUT_FUNCTIONS
    )
    return next(passed_functions, None)


def find_input_output_calls(package: Mapping[str, SourceModule], layer: Layer) -> list[str]:
    return [
        f"{module.name} calls {function}"
        for module in select_modules(package, {layer})
        for node in walk_in_source_order(module.tree)
        if isinstance(node, ast.Call) and (function := name_input_output_function(node)) is not None
    ]


def find_outer_imports_of_the_adapters(package: Mapping[str, SourceModule]) -> list[str]:
    return [
        f"{module.name} imports {imported}"
        for module in select_modules(package, {Layer.ADAPTERS})
        for imported in list_package_imports(module, package)
        if find_layer(imported) in OUTER_LAYERS_OF_THE_ADAPTERS
    ]


def find_imports_of_unrestructured_modules(package: Mapping[str, SourceModule]) -> list[str]:
    return [
        f"{module.name} imports {imported}"
        for module in select_modules(package, LAYERS)
        for imported in list_package_imports(module, package)
        if find_layer(imported) is Layer.NOT_RESTRUCTURED
    ]


def is_on_an_import_cycle(module_name: str, imports: Mapping[str, Collection[str]]) -> bool:
    visited: set[str] = set()
    pending = list(imports[module_name])
    while pending:
        current = pending.pop()
        if current == module_name:
            return True
        if current not in visited:
            visited.add(current)
            pending.extend(imports[current])
    return False


def find_modules_on_an_import_cycle(package: Mapping[str, SourceModule]) -> list[str]:
    imports = {
        name: [imported for imported in list_package_imports(module, package) if imported != name]
        for name, module in package.items()
    }
    return sorted(name for name in imports if is_on_an_import_cycle(name, imports))


def check_layers(package: Mapping[str, SourceModule]) -> LayerFindings:
    return LayerFindings(
        imports_outside_the_domain=find_imports_outside_the_domain(package),
        wall_clock_reads=find_wall_clock_reads(package),
        input_output_calls=find_input_output_calls(package, Layer.DOMAIN),
        imports_outside_the_application=find_imports_outside_the_application(package),
        application_wall_clock_reads=find_wall_clock_reads_through_their_classes(package),
        application_input_output_calls=find_input_output_calls(package, Layer.APPLICATION),
        outer_imports_of_the_adapters=find_outer_imports_of_the_adapters(package),
        imports_of_unrestructured_modules=find_imports_of_unrestructured_modules(package),
        modules_on_an_import_cycle=find_modules_on_an_import_cycle(package),
        domain_module_count=len(select_modules(package, {Layer.DOMAIN})),
        application_module_count=len(select_modules(package, {Layer.APPLICATION})),
        adapter_module_count=len(select_modules(package, {Layer.ADAPTERS})),
        layered_module_count=len(select_modules(package, LAYERS)),
        package_module_count=len(package),
    )


class TestTheLayersOfTheApi:
    class TestTheListImportedModulesFunction:
        class TestWhenAModuleImports:
            PACKAGE_MODULES = frozenset(
                {
                    "scanmylib",
                    "scanmylib.app",
                    "scanmylib.library",
                    "scanmylib.domain",
                    "scanmylib.domain.ordering",
                    "scanmylib.domain.text",
                    "scanmylib.adapters",
                    "scanmylib.adapters.sqlite",
                    "scanmylib.adapters.sqlite.database",
                    "scanmylib.adapters.sqlite.rows",
                }
            )
            IMPORT_FORMS = (
                ImportForm("a-module", "scanmylib.domain.ordering", False, "import json\n", ("json",)),
                ImportForm(
                    "a-dotted-module",
                    "scanmylib.domain.ordering",
                    False,
                    "import collections.abc\n",
                    ("collections.abc",),
                ),
                ImportForm(
                    "an-aliased-module",
                    "scanmylib.domain.ordering",
                    False,
                    "import collections.abc as abstract_collections\n",
                    ("collections.abc",),
                ),
                ImportForm(
                    "several-modules-in-one-statement",
                    "scanmylib.domain.ordering",
                    False,
                    "import json, re\n",
                    ("json", "re"),
                ),
                ImportForm(
                    "a-name-of-an-outside-module",
                    "scanmylib.domain.ordering",
                    False,
                    "from dataclasses import dataclass\n",
                    ("dataclasses",),
                ),
                ImportForm(
                    "a-submodule-of-an-outside-package-as-a-name",
                    "scanmylib.domain.ordering",
                    False,
                    "from collections import abc\n",
                    ("collections",),
                ),
                ImportForm(
                    "a-module-of-the-package-by-its-absolute-name",
                    "scanmylib.domain.text",
                    False,
                    "from scanmylib.domain import ordering\n",
                    ("scanmylib.domain.ordering",),
                ),
                ImportForm(
                    "a-dotted-module-of-the-package",
                    "scanmylib.domain.ordering",
                    False,
                    "import scanmylib.domain.text\n",
                    ("scanmylib.domain.text",),
                ),
                ImportForm(
                    "a-name-of-the-package-root-by-its-absolute-name",
                    "scanmylib.domain.ordering",
                    False,
                    "from scanmylib import API_LEVEL\n",
                    ("scanmylib",),
                ),
                ImportForm(
                    "a-name-of-a-sibling-module",
                    "scanmylib.domain.ordering",
                    False,
                    "from .text import collation_key\n",
                    ("scanmylib.domain.text",),
                ),
                ImportForm(
                    "a-sibling-module-as-a-name",
                    "scanmylib.domain.ordering",
                    False,
                    "from . import text\n",
                    ("scanmylib.domain.text",),
                ),
                ImportForm(
                    "a-name-of-a-module-two-levels-up",
                    "scanmylib.domain.ordering",
                    False,
                    "from ..library import LibraryService\n",
                    ("scanmylib.library",),
                ),
                ImportForm(
                    "a-name-of-the-package-root-two-levels-up",
                    "scanmylib.domain.ordering",
                    False,
                    "from .. import API_LEVEL\n",
                    ("scanmylib",),
                ),
                ImportForm(
                    "a-name-of-a-module-three-levels-up",
                    "scanmylib.adapters.sqlite.rows",
                    False,
                    "from ...domain.ordering import Coverage\n",
                    ("scanmylib.domain.ordering",),
                ),
                ImportForm(
                    "a-name-of-a-module-of-its-own-package-from-an-init",
                    "scanmylib.domain",
                    True,
                    "from .ordering import Coverage\n",
                    ("scanmylib.domain.ordering",),
                ),
                ImportForm(
                    "a-module-of-the-package-two-levels-up-from-an-init",
                    "scanmylib.adapters.sqlite",
                    True,
                    "from ...domain import ordering\n",
                    ("scanmylib.domain.ordering",),
                ),
                ImportForm(
                    "a-module-of-the-parent-package-from-an-init",
                    "scanmylib.domain",
                    True,
                    "from .. import app\n",
                    ("scanmylib.app",),
                ),
                ImportForm(
                    "several-modules-in-one-from-import",
                    "scanmylib.domain",
                    True,
                    "from . import ordering, text\n",
                    ("scanmylib.domain.ordering", "scanmylib.domain.text"),
                ),
                ImportForm(
                    "several-names-of-one-module",
                    "scanmylib.domain.ordering",
                    False,
                    "from typing import Literal, TypedDict\n",
                    ("typing",),
                ),
                ImportForm(
                    "every-name-of-a-module",
                    "scanmylib.domain.ordering",
                    False,
                    "from .text import *\n",
                    ("scanmylib.domain.text",),
                ),
                ImportForm(
                    "a-module-inside-a-function",
                    "scanmylib.domain.ordering",
                    False,
                    "def connect() -> None:\n    import sqlite3\n",
                    ("sqlite3",),
                ),
                ImportForm(
                    "a-module-for-the-type-checker-only",
                    "scanmylib.domain.ordering",
                    False,
                    "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from ..library import LibraryService\n",
                    ("typing", "scanmylib.library"),
                ),
                ImportForm(
                    "a-module-and-its-fallback",
                    "scanmylib.domain.ordering",
                    False,
                    "try:\n    import tomllib\nexcept ImportError:\n    import tomli\n",
                    ("tomllib", "tomli"),
                ),
                ImportForm(
                    "a-future-feature",
                    "scanmylib.domain.ordering",
                    False,
                    "from __future__ import annotations\n",
                    ("__future__",),
                ),
            )

            @pytest.fixture(params=IMPORT_FORMS, ids=[form.description for form in IMPORT_FORMS])
            def import_form(self, request: pytest.FixtureRequest) -> ImportForm:
                form: ImportForm = request.param
                return form

            @pytest.fixture
            def imported_modules(self, import_form: ImportForm) -> list[str]:
                package = parse_package({import_form.module_name: (import_form.is_package, import_form.source)})
                return list_imported_modules(package[import_form.module_name], self.PACKAGE_MODULES)

            def test_should_resolve_each_import_to_the_module_it_loads(
                self, import_form: ImportForm, imported_modules: list[str]
            ) -> None:
                assert imported_modules == list(import_form.imported_modules)

    class TestTheCheckLayersFunction:
        class TestWhenModulesBreakEachRule:
            RULE_BREAKING_PACKAGE = MappingProxyType(
                {
                    "scanmylib": (True, "API_LEVEL = 1\n"),
                    "scanmylib.app": (
                        False,
                        "from . import library\n"
                        "from .adapters.sqlite import database, rows\n"
                        "from .devtools import fake_ocr\n"
                        "from .domain import chapters, impure, numbers, pages, paragraphs, sections, titles\n",
                    ),
                    "scanmylib.library": (False, "class LibraryService:\n    pass\n"),
                    "scanmylib.devtools": (True, ""),
                    "scanmylib.devtools.fake_ocr": (False, "class FakeOcrServer:\n    pass\n"),
                    "scanmylib.domain": (True, ""),
                    "scanmylib.domain.impure": (
                        False,
                        "import asyncio\n"
                        "import re\n"
                        "import sqlite3\n"
                        "from datetime import date, datetime\n"
                        "\n"
                        "from ..library import LibraryService\n"
                        "\n"
                        "MOMENT = datetime.now()\n"
                        "TODAY = date.today\n"
                        "SCAN = open('scan.jpg')\n"
                        "CONNECTION = asyncio.open_connection('localhost', 8765)\n"
                        "PAGE_PATTERN = re.compile('page')\n",
                    ),
                    "scanmylib.domain.pages": (False, "from . import numbers\n"),
                    "scanmylib.domain.numbers": (False, "from .pages import PAGE\n"),
                    "scanmylib.domain.chapters": (False, "from .sections import SECTION\n"),
                    "scanmylib.domain.sections": (False, "from .paragraphs import PARAGRAPH\n"),
                    "scanmylib.domain.paragraphs": (False, "from . import chapters\n"),
                    "scanmylib.domain.titles": (
                        False,
                        "import re\nfrom dataclasses import dataclass\n\nfrom .pages import PAGE\n",
                    ),
                    "scanmylib.application": (True, ""),
                    "scanmylib.application.clock": (
                        False,
                        "from datetime import datetime\n"
                        "from typing import Protocol\n"
                        "\n"
                        "\n"
                        "class Clock(Protocol):\n"
                        "    def now(self) -> datetime: ...\n",
                    ),
                    "scanmylib.application.sessions": (
                        False,
                        "import asyncio\n"
                        "import hashlib\n"
                        "import hmac\n"
                        "import logging\n"
                        "import secrets\n"
                        "from contextlib import suppress\n"
                        "from pathlib import PurePath as Location\n"
                        "\n"
                        "from ..domain.titles import TITLE\n"
                        "from .clock import Clock\n"
                        "\n"
                        "\n"
                        "def read_the_moment(clock: Clock) -> float:\n"
                        "    return clock.now().timestamp()\n"
                        "\n"
                        "\n"
                        "def read_the_loop_time() -> float:\n"
                        "    return asyncio.get_running_loop().time()\n",
                    ),
                    "scanmylib.application.impure": (
                        False,
                        "import asyncio\n"
                        "import datetime as moments\n"
                        "import pathlib\n"
                        "import sqlite3\n"
                        "import time\n"
                        "from datetime import date, datetime\n"
                        "from datetime import datetime as Moment\n"
                        "from pathlib import *\n"
                        "from pathlib import Path, PurePath\n"
                        "\n"
                        "from ..adapters.sqlite import database\n"
                        "\n"
                        "MOMENT = datetime.now()\n"
                        "TODAY = date.today\n"
                        "ALIASED_MOMENT = Moment.now()\n"
                        "UNIVERSAL_MOMENT = moments.datetime.utcnow()\n"
                        "SCAN = open('scan.jpg')\n"
                        "SERVER = asyncio.start_unix_server(None, 'ocr.sock')\n"
                        "PROCESS = asyncio.get_running_loop().subprocess_exec(None, 'ocr')\n"
                        "STARTED = time.time()\n"
                        "THREADED_SCAN = asyncio.to_thread(open, 'scan.jpg')\n"
                        "PRINTED = asyncio.get_running_loop().run_in_executor(None, print, 'scan')\n"
                        "ADDRESSES = asyncio.get_running_loop().getaddrinfo('example.invalid', 80)\n"
                        "CALLBACK = asyncio.get_running_loop().call_soon(callback=print)\n",
                    ),
                    "scanmylib.adapters": (True, ""),
                    "scanmylib.adapters.sqlite": (True, ""),
                    "scanmylib.adapters.sqlite.rows": (
                        False,
                        "from ... import API_LEVEL\n"
                        "from ...devtools.fake_ocr import FakeOcrServer\n"
                        "from ...library import LibraryService\n",
                    ),
                    "scanmylib.adapters.sqlite.database": (
                        False,
                        "import sqlite3\n\nfrom ...domain.titles import TITLE\n",
                    ),
                }
            )

            @pytest.fixture
            def findings(self) -> LayerFindings:
                return check_layers(parse_package(self.RULE_BREAKING_PACKAGE))

            def test_should_name_each_import_of_the_domain_that_is_neither_the_domain_nor_its_allowlist(
                self, findings: LayerFindings
            ) -> None:
                assert findings.imports_outside_the_domain == [
                    "scanmylib.domain.impure imports asyncio",
                    "scanmylib.domain.impure imports sqlite3",
                    "scanmylib.domain.impure imports scanmylib.library",
                ]

            def test_should_name_each_read_of_the_wall_clock_in_the_domain_called_or_not(
                self, findings: LayerFindings
            ) -> None:
                assert findings.wall_clock_reads == [
                    "scanmylib.domain.impure reads now",
                    "scanmylib.domain.impure reads today",
                ]

            def test_should_name_each_input_or_output_call_in_the_domain_but_not_a_compiled_pattern(
                self, findings: LayerFindings
            ) -> None:
                assert findings.input_output_calls == [
                    "scanmylib.domain.impure calls open",
                    "scanmylib.domain.impure calls open_connection",
                ]

            def test_should_name_each_import_of_the_application_that_is_neither_an_inner_layer_nor_its_allowlist(
                self, findings: LayerFindings
            ) -> None:
                assert findings.imports_outside_the_application == [
                    "scanmylib.application.impure imports pathlib",
                    "scanmylib.application.impure imports sqlite3",
                    "scanmylib.application.impure imports time",
                    "scanmylib.application.impure imports pathlib.*",
                    "scanmylib.application.impure imports pathlib.Path",
                    "scanmylib.application.impure imports scanmylib.adapters.sqlite.database",
                ]

            def test_should_name_each_wall_clock_read_through_its_classes_in_the_application_but_not_through_its_port(
                self, findings: LayerFindings
            ) -> None:
                assert findings.application_wall_clock_reads == [
                    "scanmylib.application.impure reads datetime.now",
                    "scanmylib.application.impure reads date.today",
                    "scanmylib.application.impure reads Moment.now",
                    "scanmylib.application.impure reads datetime.utcnow",
                ]

            def test_should_name_each_input_or_output_call_in_the_application(self, findings: LayerFindings) -> None:
                assert findings.application_input_output_calls == [
                    "scanmylib.application.impure calls open",
                    "scanmylib.application.impure calls start_unix_server",
                    "scanmylib.application.impure calls subprocess_exec",
                    "scanmylib.application.impure calls open",
                    "scanmylib.application.impure calls print",
                    "scanmylib.application.impure calls getaddrinfo",
                    "scanmylib.application.impure calls print",
                ]

            def test_should_name_each_composition_root_and_test_support_that_an_adapter_imports(
                self, findings: LayerFindings
            ) -> None:
                assert findings.outer_imports_of_the_adapters == [
                    "scanmylib.adapters.sqlite.rows imports scanmylib",
                    "scanmylib.adapters.sqlite.rows imports scanmylib.devtools.fake_ocr",
                ]

            def test_should_name_each_unrestructured_module_that_a_layered_module_imports(
                self, findings: LayerFindings
            ) -> None:
                assert findings.imports_of_unrestructured_modules == [
                    "scanmylib.adapters.sqlite.rows imports scanmylib.library",
                    "scanmylib.domain.impure imports scanmylib.library",
                ]

            def test_should_name_every_module_on_an_import_cycle_and_only_those(self, findings: LayerFindings) -> None:
                assert findings.modules_on_an_import_cycle == [
                    "scanmylib.domain.chapters",
                    "scanmylib.domain.numbers",
                    "scanmylib.domain.pages",
                    "scanmylib.domain.paragraphs",
                    "scanmylib.domain.sections",
                ]

    class TestWhenTheModulesOfTheApiAreRead:
        @pytest.fixture(scope="class")
        @classmethod
        def layers(cls) -> PackageLayers:
            layered_directories = [PACKAGE_DIRECTORY / directory for directory in ("domain", "application", "adapters")]
            return PackageLayers(
                findings=check_layers(read_package(PACKAGE_DIRECTORY)),
                domain_file_count=count_python_files(PACKAGE_DIRECTORY / "domain"),
                application_file_count=count_python_files(PACKAGE_DIRECTORY / "application"),
                adapter_file_count=count_python_files(PACKAGE_DIRECTORY / "adapters"),
                layered_file_count=sum(count_python_files(directory) for directory in layered_directories),
                package_file_count=count_python_files(PACKAGE_DIRECTORY)
                - count_python_files(PACKAGE_DIRECTORY / WEB_UI_DIRECTORY),
            )

        def test_should_import_only_the_domain_and_its_allowlist_from_the_domain(self, layers: PackageLayers) -> None:
            assert layers.domain_file_count > 0
            assert layers.findings.domain_module_count == layers.domain_file_count
            assert layers.findings.imports_outside_the_domain == []

        def test_should_read_no_wall_clock_in_the_domain(self, layers: PackageLayers) -> None:
            assert layers.domain_file_count > 0
            assert layers.findings.domain_module_count == layers.domain_file_count
            assert layers.findings.wall_clock_reads == []

        def test_should_call_no_input_or_output_function_in_the_domain(self, layers: PackageLayers) -> None:
            assert layers.domain_file_count > 0
            assert layers.findings.domain_module_count == layers.domain_file_count
            assert layers.findings.input_output_calls == []

        def test_should_import_only_the_inner_layers_and_its_allowlist_from_the_application(
            self, layers: PackageLayers
        ) -> None:
            assert layers.application_file_count > 0
            assert layers.findings.application_module_count == layers.application_file_count
            assert layers.findings.imports_outside_the_application == []

        def test_should_read_the_wall_clock_only_through_its_port_in_the_application(
            self, layers: PackageLayers
        ) -> None:
            assert layers.application_file_count > 0
            assert layers.findings.application_module_count == layers.application_file_count
            assert layers.findings.application_wall_clock_reads == []

        def test_should_call_no_input_or_output_function_in_the_application(self, layers: PackageLayers) -> None:
            assert layers.application_file_count > 0
            assert layers.findings.application_module_count == layers.application_file_count
            assert layers.findings.application_input_output_calls == []

        def test_should_import_no_composition_root_and_no_test_support_from_the_adapters(
            self, layers: PackageLayers
        ) -> None:
            assert layers.adapter_file_count > 0
            assert layers.findings.adapter_module_count == layers.adapter_file_count
            assert layers.findings.outer_imports_of_the_adapters == []

        def test_should_import_no_module_still_outside_the_layers_from_a_layered_module(
            self, layers: PackageLayers
        ) -> None:
            assert layers.layered_file_count > 0
            assert layers.findings.layered_module_count == layers.layered_file_count
            assert layers.findings.imports_of_unrestructured_modules == []

        def test_should_hold_no_import_cycle(self, layers: PackageLayers) -> None:
            assert layers.package_file_count > 0
            assert layers.findings.package_module_count == layers.package_file_count
            assert layers.findings.modules_on_an_import_cycle == []
