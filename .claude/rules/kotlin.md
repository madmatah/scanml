---
paths:
  - "android/**/*.kt"
  - "android/**/*.kts"
  - "android/**/*.xml"
---

# Kotlin

The Android app (`android/`) is written in Kotlin, with Jetpack Compose and coroutines, from the Kotlin coding
conventions (kotlinlang.org), Android's Kotlin style guide and the guides of Compose and coroutines. These rules come on
top of `conventions.md`.

- **The Kotlin coding conventions, at 120 columns.**
- **Casing:** `PascalCase` for classes and objects, `camelCase` for functions and properties, `UPPER_SNAKE_CASE` for
  `const val`. Packages are lowercase (`fr.scanmylib.library`), and a file is named after its main declaration. Acronyms
  are always written as words (`OcrClient`, `pageId`, `UiState`), as Android's style guide writes them, where the Kotlin
  conventions would capitalize one of two letters (`IOStream`).
- **No `!!` and no `lateinit`.** Use `?.`, `?:`, or `requireNotNull(…) { "why" }` where a null would be a bug. A value
  from a Java API gets an explicit nullable or non-null type at once, since Kotlin cannot check a platform type. A test
  class alone holds what its hooks produce in a `lateinit var`, or, for a primitive or a value class, which `lateinit`
  refuses, in a `var` delegated to `Delegates.notNull()`, and a product that may be null inside a non-null value held
  that way: JUnit builds the class before its hooks run, and both throw when a test reads them before a hook set them.
- **Immutable by default:** `val`, and read-only `List` and `Map` in signatures. Mutable state is private
  (`private val mutableState = MutableStateFlow(…)`) and shown read-only through `asStateFlow()`.
- **A closed set is a `sealed interface` or an `enum class`, and a `when` over one lists every case, without `else`,**
  so that a new case fails to compile wherever it is forgotten.
- **Data that is stored or sent is a `data class` of `val`s, annotated `@Serializable`** (kotlinx.serialization).
- **The narrowest visibility:** `private`, unless another file uses it, or a test framework reaches it by reflection, as
  JUnit reaches a test class's groups, tests and hooks.
- **Structured coroutines.** A coroutine is launched only in a scope tied to a lifecycle: `viewModelScope`, the
  application's scope in `AppContainer`, or a `CoroutineWorker`. No `GlobalScope`, and `runBlocking` only in tests.
  Dispatchers are parameters with a default (`io: CoroutineDispatcher = Dispatchers.IO`), so that tests run the code on
  a test dispatcher, which they control.
- **Cancellation is never swallowed.** A `catch` of `Exception` or `Throwable` in suspending code rethrows
  `CancellationException` first. Catch the narrowest exception; a broad catch only at a boundary, such as a call to the
  PC or a worker, which turns the failure into a state.
- **Compose:** a composable that emits UI is named as a noun in `PascalCase` (`PageThumbnail`), takes its state and its
  events as parameters (state hoisting), and takes `modifier: Modifier = Modifier` as its first optional parameter.
  Every text of the UI comes from the string resources (`stringResource`), since its French translation lives in
  `values-fr/`.
- **Idioms that override the naming rules:** `it` in a short lambda; `e` for a caught exception; test names in
  backticks, as sentences, and test groups named as their phrase (`TheHintForMethod`, `WhenThePagesAreConsecutive`), in
  tests only; composables named as nouns; and the names Android imposes (`onCreate`, `doWork`).
- **Directives:** `@Suppress("ID")` (`@Suppress("ktlint:standard:<rule>")` for ktlint), `@SuppressLint("ID")` and
  `tools:ignore`, each with its reason; `@OptIn(…)` for an experimental API, on the narrowest declaration.
