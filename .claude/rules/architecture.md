---
paths:
  - "server/**"
  - "ocr/**"
  - "android/**"
  - "scripts/**"
---

# Architecture

The project follows Clean Architecture, in four layers, and applies SOLID to modules, functions and types. The api
(`server/scanmylib/`), the app (`android/app/src/main/kotlin/fr/scanmylib/`), the web UI (`server/scanmylib/web/`) and
the OCR sandbox (`ocr/scanmylib_ocr/`) each follow these rules within their own source tree. The scripts of `scripts/`
are tools: their logic lives in `scripts/lib/`, and they follow the rules of SOLID.

## Layers

- **Four layers, from the inside out:** the domain, the application, the adapters and the composition roots. A module's
  layer is the directory it lives in: `domain/`, `application/` and `adapters/` of its unit's source tree, with the
  composition roots at its top.
- **Dependencies point inward.** An inner layer never refers to an outer one: no import, no type, no name. The domain
  depends only on the domain, the application on the domain, the adapters on the application and the domain, and the
  composition roots on every layer. A library of plain values that does no I/O and reads no clock may serve any layer.
- **No dependency cycle,** between modules of the same layer included.
- **The api reaches the OCR engine only through the sandbox protocol** (`docs/OCR_SANDBOX.md`): its OCR port, which the
  sandbox implements in its own process, and the fake OCR in the development stack. The api never depends on a
  particular engine or model, so that another one can be plugged in by implementing a new worker.
- **The code written before these layers keeps its layout until it is restructured,** which is planned for the api, the
  app and the web UI, not yet for the OCR sandbox. Until then, a new module follows the layers, and a change to an older
  one adds no coupling that they forbid: no technology reached from code that holds a rule, no rule in an adapter, no
  framework type across a port. A module in a layer's directory, moved or new, imports none that is still outside the
  layers, which would bring it that module's couplings.

## Ports and wiring

- **Inner layers own their ports.** When the application needs the outside world, it declares an interface in its own
  vocabulary, and an adapter implements it. The application reaches a technology only through that port: the database,
  the library's files, the OCR sandbox, the HTTP API of the PC, the camera, the clock.
- **Only composition roots wire.** The entry points of each unit (the api's `scanmylib.__main__` and the application
  factory it calls, the app's `ScanMyLibApplication`, `AppContainer` and `MainActivity`, the web UI's `main.js`, the
  sandbox's `supervisor`, `worker` and `engine_environment`) and the tests choose and connect the concrete adapters, by
  hand: written by hand, the graph stays in one place and checked by the types, where a DI container would resolve it at
  run time, by tokens. No DI container, no service locator, no singleton, and no module-level mutable state shared
  between callers.
- **Plain data crosses boundaries:** values whose types belong to the inner side. No framework or platform type crosses
  a port: no FastAPI request, no `sqlite3.Row`, no Android `Uri` or `Context`.
- **A location crosses a port as a value that names its file and cannot open it,** so that an inner layer does no I/O
  that its types or its review would not show; only an adapter that reads or writes that file opens it.
- **A module's public API is its single entry point.** Everything else is internal, and nothing reaches inside another
  module.

## Responsibilities

- **The domain holds the rules and is pure:** no I/O, no clock, no global mutable state, no framework, no platform API.
  The rules of page numbering and of the reading order are the domain's.
- **The application orchestrates.** It passes the inputs to the domain, calls its ports and assembles the result. Any
  rule it needs belongs in the domain.
- **Adapters translate, nothing more.** An adapter converts between a technology and an inner layer, through a port or
  through the plain data the inner layer defines, and is named after that technology. It holds no business rule.
- **Composition roots decide no rule either.** They wire the adapters, and turn outside input into the requests of the
  inner layers.
- **OCR output is kept as the engine produces it.** No code compensates for the mistakes of a particular model, and raw
  LaTeX stays as it is: the display is fixed generically, as KaTeX renders formulas in the web UI.
- **Nothing is hard-deleted from the library:** a deleted document or page moves to `LIBRARY_DIR/.trash/`.

## Stored and shared data

- **What is stored, sent, or crosses a thread or a process is plain data:** values in the types of the inner side that
  survive a round trip through their serialized form unchanged, with no handle, no closure, and nothing the
  serialization drops or alters. It then saves, travels and replays as it is. This covers the rows of the api's
  database, the files of the library (`document.json`, `library.json`, the Markdown), the JSON of the HTTP API, the
  messages of the sandbox protocol, and the app's database, upload queue and settings. Elsewhere, a type may hold
  behavior.

## SOLID

- **Single responsibility.** A module, a function or a type has one reason to change, and a file holds one concept. A
  function whose name needs an "and" does two things. When a change to one rule forces edits across unrelated concepts,
  the responsibilities are mixed.
- **Open for extension.** A new case is added as data, or beside the existing cases, without rewriting the code that
  handles them.
- **Substitutable implementations.** Every implementation of a port, the fakes of the tests and the fake OCR included,
  honors its whole contract: units, ordering, errors, missing values. The application behaves the same on a fake and on
  the real adapter.
- **Narrow ports.** A port offers only what its client uses, in the client's vocabulary, and nothing depends on methods
  it does not call.
- **Dependency inversion.** Policy depends on the abstractions it owns, the ports of the inner layers, never on a
  concrete technology.
- **No speculative generality:** no abstraction with a single caller and no rule behind it.

## Organization

- **Folders, files and modules are named after domain concepts,** never after technical kinds: `utils`, `helpers`,
  `services`, `models` or `common`, nor their singulars.
