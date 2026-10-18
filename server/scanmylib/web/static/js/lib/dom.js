/**
 * Small DOM helpers.
 *
 * Strings are always inserted as text nodes, never parsed as HTML: titles,
 * authors and file names come from users and phones. The only HTML the UI
 * inserts as-is is the OCR preview, which the server sanitizes.
 */

/** Keys set as element properties rather than attributes. */
const PROPERTIES = new Set(['value', 'checked', 'indeterminate']);

/**
 * Creates an element: `h('a', { class: 'btn', href: '#/' }, t('Library'))`.
 *
 * - `class` takes a string or an array (falsy entries are dropped);
 * - `dataset` and `style` take objects;
 * - `onClick`, `onSubmit`… add event listeners;
 * - any other key becomes an attribute: `true` gives an empty attribute,
 *   `false`, `null` and `undefined` leave it out.
 *
 * Children may be nodes, strings, numbers, nested arrays or falsy values
 * (skipped).
 */
export function h(tag, props = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === false || value === null || value === undefined) continue;
    if (key === 'class') {
      element.className = Array.isArray(value) ? value.filter(Boolean).join(' ') : value;
    } else if (key === 'dataset' || key === 'style') {
      Object.assign(element[key], value);
    } else if (/^on[A-Z]/.test(key)) {
      element.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (PROPERTIES.has(key)) {
      element[key] = value;
    } else {
      element.setAttribute(key, value === true ? '' : String(value));
    }
  }
  appendChildren(element, children);
  return element;
}

/** Replaces the children of `parent`, with the same rules as h() (falsy values skipped). */
export function setChildren(parent, ...children) {
  parent.replaceChildren();
  appendChildren(parent, children);
}

/** Appends nodes and strings (nested arrays allowed, falsy values skipped). */
function appendChildren(parent, children) {
  for (const child of [children].flat(Infinity)) {
    if (child === false || child === null || child === undefined) continue;
    parent.append(child);
  }
}

let idCounter = 0;

/** Returns an id unique in the page, for label/aria associations. */
export function uniqueId(prefix) {
  idCounter += 1;
  return `${prefix}-${idCounter}`;
}

/**
 * Makes `nodes` the exact children of `parent`, in order. Nodes already in
 * place are left untouched, so periodic refreshes keep keyboard focus and
 * loaded images.
 */
export function syncChildren(parent, nodes) {
  let cursor = parent.firstChild;
  for (const node of nodes) {
    if (node === cursor) {
      cursor = cursor.nextSibling;
    } else {
      parent.insertBefore(node, cursor);
    }
  }
  while (cursor) {
    const next = cursor.nextSibling;
    cursor.remove();
    cursor = next;
  }
}

/**
 * Remembers rendered nodes by key and renders them again only when their
 * signature (a string summarizing the displayed data) changes.
 */
export class NodeCache {
  #entries = new Map();

  get(key, signature, render) {
    const entry = this.#entries.get(key);
    if (entry && entry.signature === signature) {
      entry.used = true;
      return entry.node;
    }
    const node = render();
    this.#entries.set(key, { signature, node, used: true });
    return node;
  }

  /** Forgets the nodes that were not requested since the previous prune. */
  prune() {
    for (const [key, entry] of this.#entries) {
      if (entry.used) entry.used = false;
      else this.#entries.delete(key);
    }
  }
}

/** True when the keyboard event happens in a text field (shortcuts must not fire). */
export function isTypingTarget(target) {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
  );
}
