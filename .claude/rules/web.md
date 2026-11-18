---
paths:
  - "server/scanmylib/web/**"
---

# The web UI

The web UI (`server/scanmylib/web/`) is written in TypeScript and React, in `src/`, and built by a bundler into the
files that the api serves. These rules come on top of `conventions.md`.

## TypeScript and React

From the TypeScript handbook and React's "Rules of React" (react.dev).

- **Strict,** with `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`, as the base `tsconfig` sets them.
- **Named exports only.** A configuration file that a tool reads through its default export is the exception, such as
  the bundler's.
- **Erasable syntax only:** no `enum` and no `namespace`, but unions of literals and `as const` objects, so that the
  tools strip the types without a compiler. Relative imports carry their `.ts` or `.tsx` extension, so that the tests of
  plain modules run with `node --test` as they are.
- **No `any`.**
- **A switch over a union whose cases must all be handled ends with a `never` check,** in a `default` that throws,
  unless each case returns a value that the function's return type requires, which the compiler checks itself: a new
  case then fails to compile at every switch that forgets it.
- **A function passed as a callback does not depend on `this`.** A factory's functions close over their state, and a
  callback that needs an object's method wraps it (`() => view.render()`). Neither the compiler nor the linter catches
  an unbound method.
- **Function components and hooks only,** never a class component.
- **Rendering is pure.** A component computes its JSX from its props and its state, with no side effect. An effect
  (`useEffect`) only synchronizes with a system outside React, never computes derived state.
- **The rules of hooks:** a hook is called at the top level of a component or of another hook, never in a condition or a
  loop, and a custom hook is named `useSomething`.
- **A `key` comes from the identity of the data,** such as a page's id, never from its index in the array, which changes
  when the pages are reordered.
- **State is immutable:** it is replaced by a new value, never changed in place.
- **`dangerouslySetInnerHTML` only takes the HTML that the server's allowlist sanitizer produced,** in the page preview
  and the reader, under the Content Security Policy. Every other text is rendered as text by JSX, and a URL from outside
  is checked before it reaches an `href` or a `src`.
- **No `as` cast on outside data:** the api client checks the shape of each response before it becomes a typed value.
- **Layout:** 2-space indentation, semicolons, single quotes, template literals for interpolation, 120 columns.
- **Casing:** `camelCase` for functions and variables, `PascalCase` for types and components, `UPPER_SNAKE_CASE` for
  module constants. Files are named in `kebab-case` (`page-organizer.tsx`), and their tests `<module>.test.ts`. Acronyms
  are written as words (`ApiError`).
- **`async` and `await`, and no floating promise:** every promise is awaited, or handled where it is created.
- **Every text of the UI goes through `t()`** (the translation function), so that its French translation lives in the
  catalog, as `CLAUDE.md` > Language says.
- **Idioms that override the naming rules:** `t()`, the translation function; event props named `onSomething`; and the
  names the DOM and React impose.
- **Directives:** the linter's suppression comment, with its reason, and `@ts-expect-error`, which fails once its error
  is gone. `@ts-ignore` and `@ts-nocheck` are refused: they outlive the errors they silence.

