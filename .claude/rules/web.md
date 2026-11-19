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
- **Every function is declared as a `const` arrow function,** `export const pageTitle = (page: Page): string => { … };`,
  never with a `function` declaration, exported or not, nested, in the tests, and components included: one form for
  every function, and a module that reads top-down, since a `const` exists only from its line on, so that a helper
  comes before the code that runs it at load. A generic one in a `.tsx` file is written `<Entry,>(…) =>`, which JSX
  would otherwise read as a tag. The one exception is a function that needs its own `this`, such as one that replaces a
  method of a prototype, which an arrow function cannot have: it stays a `function` expression. Biome's plugin
  `biome-plugins/arrow-functions.grit` refuses a `function` declaration.
- **A switch over a union whose cases must all be handled ends with a `never` check,** in a `default` that throws,
  unless each case returns a value that the function's return type requires, which the compiler checks itself: a new
  case then fails to compile at every switch that forgets it.
- **A function passed as a callback does not depend on `this`.** A factory's functions close over their state, and a
  callback that needs an object's method wraps it (`() => view.render()`). Neither the compiler nor the linter catches
  an unbound method.
- **Function components and hooks only,** never a class component.
- **A component is typed `FC<Props>`,** `export const PageGrid: FC<PageGridProps> = ({ pages }) => { … };`, with
  `import type { FC } from 'react';`, or `FC` alone when it takes no props: the type says at its name that it is a
  component, and checks what it returns. `FC` adds no `children`: a component that takes them declares them in its
  props. A generic component is the exception, typed by its parameters, such as
  `export const DocumentDialog = <Saved,>({ … }: DocumentDialogProps<Saved>) => { … };`: a variable's type cannot
  introduce a type parameter, and `FC<DocumentDialogProps<unknown>>` would refuse its callers' typed callbacks. Biome's
  plugin `biome-plugins/typed-components.grit` refuses, in a `.tsx` file, a `PascalCase` constant set to an arrow
  function that is neither typed nor generic.
- **Rendering is pure.** A component computes its JSX from its props, with no side effect. An effect, in a hook, only
  synchronizes with a system outside React, never computes derived state.
- **A component renders.** It calls no hook but `useTranslation`, `useId`, `useRef` for an element it renders, to focus
  it or click a hidden input, and the project's hooks that the next rules give it. An event handler may guard on a prop
  it was given and act on its own element, then call a callback it was given: the page's `IconButton` ignores a click
  while `isUnavailable`, a header link prevents a click on the address given as the current one, a file input reads and
  clears its files before passing them on. State, effects, timers, the application, navigation, toasts and any value
  the component was not given belong to a hook. A component then reads as its markup, and the logic lies where
  `node --test` reaches it, since the web UI has no screen tests. `memo`, `createPortal` and `Trans` render, and stay
  in components. Biome's plugin `biome-plugins/stateless-components.grit` refuses, in a `.tsx` file, a named import
  from `react`, `react-dom`, `react-router` or `react-router/dom` whose imported name, behind any alias, starts with
  `use`, `unstable_use` or `UNSAFE_use`, but `useId` and `useRef`, so that a hook that a later release adds is refused
  too, and a default or namespace import of those packages, which reaches the same hooks as its members. Review keeps
  what an import cannot show:
  - a `.ts` module that wraps or re-exports a React or React Router hook for a component;
  - a leaf that calls a root's hook, or an element hook that calls the application, since the plugin cannot tell the
    kind of a project's hook;
  - a ref that holds a value rather than reaching an element;
  - a handler that decides more than this rule allows.
- **A stateful root has one hook,** `use-<root>.ts` beside its component, which holds the root's state, effects,
  timers, subscriptions to the application's stores, calls to the application, navigation and toasts. Only the root's
  component calls it, and passes data and callbacks down; the hook may compose smaller hooks of its own directory, and
  the shared hooks `dialogs/use-modal.ts`, which a dialog's root hook calls for the dialog's modality and focus, as a
  dialog's leaf does, and `shell/use-document-title.ts`, which a screen's hook calls for the title of the browser's
  tab. The roots:
  - the six screens, library, pairing, login, document, page and reader, whose hook is `use-<name>-screen.ts`
    (`useLibraryScreen`);
  - the shell (`use-shell.ts`), the frame around every screen;
  - the Organize mode (`use-page-organizer.ts`), mounted inside the document screen with a store and a lifetime of its
    own;
  - each dialog with a form (`use-document-dialog.ts`, `use-move-dialog.ts`), whose form lives and dies with the
    dialog;
  - the uploader (`use-uploader.ts`), whose progress changes many times a second: read in the document screen's hook,
    each change would render the whole document screen, its page grid included.
- **An element hook binds an element that a leaf renders to the browser:** its effects and listeners, its layout, its
  focus, the HTML placed in it, and the small state that only the browser determines, such as the page under the
  reader's reading line. It lives in a `use-*.ts` file of its own, takes values and callbacks, returns refs and that
  state, and never calls the application: no port, no store, no toast, no navigation and no router hook, so that a
  value such as the reader's address comes as an argument from the root's hook. The leaf that renders the element calls
  it and renders what it returns: the element can mount after its root, once the screen has loaded, and the hook's
  effects then run with it, where a root's hook binding it through a callback ref would unbind and bind it again each
  time the ref's inputs change. The element hooks are `use-modal.ts` (a dialog's modality and focus),
  `use-sanitized-html.ts` (the sanitized HTML placed in an element), `use-scan-layout.ts` (the scan's layout),
  `use-page-text.ts` (a page's text), `use-page-number-field.ts` (the page number's field), `use-reader-text.ts` (the
  reader's text and the page under its reading line) and `use-panel-dismissal.ts` (the engine panel closed by a click
  outside or Escape); a new one passes the same test.
- **A route component reads its id and keys its screen:** `DocumentScreen`, `PageScreen` and `ReaderScreen` read the
  id that the address names with `useRouteId` (`shell/use-route-id.ts`), and render their screen keyed by it, whose
  component calls the screen's hook. Each id then starts afresh, its dialogs, its Organize mode and its loaders
  included, where a reset inside the hook would rebuild by hand what a key does.
- **What can be pure goes down** to the application or the domain, where `node --test` tests it. What binds React, the
  DOM or the router stays in a hook: refs, focus, pointer and keyboard events, the listeners of `window` and
  `document`, `ResizeObserver`, `requestAnimationFrame`, `flushSync`, `document.title`, `history.replaceState`, the
  template that parses the sanitized HTML, and the routes.
- **The rules of hooks:** a hook is called at the top level of a component or of another hook, never in a condition or a
  loop, and a custom hook is named `useSomething`. A component calls only the hooks that "A component renders" gives
  it.
- **A `key` comes from the identity of the data,** such as a page's id, never from its index in the array, which changes
  when the pages are reordered.
- **State is immutable:** it is replaced by a new value, never changed in place.
- **`dangerouslySetInnerHTML` only takes the HTML that the server's allowlist sanitizer produced,** in the page preview
  and the reader, under the Content Security Policy. Every other text is rendered as text by JSX, and a URL from outside
  is checked before it reaches an `href` or a `src`.
- **No `as` cast on outside data:** the api client checks the shape of each response before it becomes a typed value.
- **Layout:** 2-space indentation, semicolons, single quotes, template literals for interpolation, 120 columns.
- **Casing:** `camelCase` for functions and variables, `PascalCase` for types and components, `UPPER_SNAKE_CASE` for
  module constants. Files are named in `kebab-case` (`page-organizer.tsx`). Acronyms are written as words (`ApiError`).
- **`async` and `await`, and no floating promise:** every promise is awaited, or handled where it is created.
- **Every text of the UI goes through `t()`** (the translation function), so that its French translation lives in the
  catalog, as `CLAUDE.md` > Language says.
- **Idioms that override the naming rules:** `t()`, the translation function; event props named `onSomething`; and the
  names the DOM and React impose.
- **Directives:** the linter's suppression comment, with its reason, and `@ts-expect-error`, which fails once its error
  is gone. `@ts-ignore` and `@ts-nocheck` are refused: they outlive the errors they silence.

