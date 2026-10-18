/**
 * "Organize pages": the reading order of a document as a grid of page
 * cards, to select and move pages by dragging them (mouse, touch and pen,
 * with Pointer Events: the HTML drag-and-drop API does not work on touch
 * screens), with the buttons of each card, or with the "Move selection…"
 * dialog.
 *
 * A move is shown at once, then the whole order is sent to
 * PUT /api/documents/{id}/order. Moves made while that request runs are sent
 * together right after it. The document returned by the server is shown once
 * nothing is being dragged or sent. A 409 means that pages joined or left the
 * reading order meanwhile (OCR finished, page excluded…): the document is
 * reloaded and the user moves the pages again on the fresh list.
 */
import { ApiError, versionedUrl } from '../api.js';
import { h, setChildren, syncChildren, uniqueId } from '../lib/dom.js';
import { errorMessage } from '../lib/errors.js';
import { t, tn } from '../lib/i18n.js';
import { pagePlacement, pageShortLabel, pageTitle } from '../lib/labels.js';
import {
  autoScrollStep,
  columnGap,
  dropTarget,
  inOrder,
  insertionMark,
  moveBlock,
  moveByOne,
  moveNextTo,
  rangeOf,
  sameOrder,
  spanOf,
} from '../lib/order.js';
import { confirmDialog, openModal } from './dialogs.js';
import { icon } from './icons.js';
import { toast } from './toast.js';

/** Mouse movement that turns a press into a drag; less is a click. In px. */
const DRAG_THRESHOLD_PX = 5;
/** Touch or pen movement that means the page is being scrolled, before a long press. In px. */
const SCROLL_SLOP_PX = 10;
/** Touch or pen: holding a card this long picks it up (its grip handle picks it up at once). */
const LONG_PRESS_MS = 400;
/** The click that ends a drag or a long press is ignored if it comes within this delay. */
const CLICK_AFTER_DRAG_MS = 400;
/** The dragged image is drawn this far from a mouse pointer, or this far above a finger. In px. */
const GHOST_MOUSE_OFFSET_PX = 14;
const GHOST_FINGER_GAP_PX = 28;
/** Layout changes smaller than this are ignored during a drag, in px. */
const LAYOUT_TOLERANCE_PX = 0.5;

const conflictMessage = () => t('The list of pages changed: try again.');

const isPresent = (value) => value !== null && value !== undefined;

/** "the page at position 21 (p. 1)": for screen readers, unnumbered pages all look alike. */
function pageName(page, position) {
  return page.page_label
    ? t('the page at position {position} (p. {label})', { position: position + 1, label: page.page_label })
    : t('the page at position {position} (no number)', { position: position + 1 });
}

/** Buttons are marked aria-disabled rather than disabled, so that a focused button keeps the focus. */
function setUnavailable(button, unavailable) {
  if (unavailable) button.setAttribute('aria-disabled', 'true');
  else button.removeAttribute('aria-disabled');
}

function isUnavailable(button) {
  return button.getAttribute('aria-disabled') === 'true';
}

/**
 * Badge telling how a page of the reading order got its place, or null for
 * pages placed by their number. "to place" only means something when other
 * pages have a place (`withUnplaced`).
 */
export function placementChip(page, withUnplaced) {
  if (page.placement === 'unplaced' && !withUnplaced) return null;
  const placement = pagePlacement(page.placement);
  return (
    placement &&
    h(
      'span',
      {
        class: ['chip', 'chip-placement', `placement-${page.placement}`],
        title: placement.description,
      },
      placement.label,
    )
  );
}

/** The thumbnail that follows the pointer, with the number of pages moved. */
function dragGhost(card, count) {
  const image = card.querySelector('.page-thumb img');
  return h(
    'div',
    { class: 'drag-ghost', 'aria-hidden': 'true' },
    image && h('img', { src: image.currentSrc || image.src, alt: '', draggable: 'false' }),
    count > 1 && h('span', { class: 'drag-ghost-count' }, String(count)),
  );
}

/**
 * "Move selection…": before or after which page. `choices` are
 * `{ id, label, name }`. Resolves with `{ targetId, side }`, or null.
 */
function moveDialog({ count, choices }) {
  return new Promise((resolve) => {
    const ids = { title: uniqueId('dialog-title'), target: uniqueId('move-target'), summary: uniqueId('move-summary') };
    const sideChoices = [
      ['before', t('before')],
      ['after', t('after')],
    ];
    const sides = sideChoices.map(([value, label]) =>
      h(
        'label',
        { class: 'segmented-option' },
        h('input', { type: 'radio', name: 'side', value, checked: value === 'before' }),
        h('span', {}, label),
      ),
    );
    const target = h(
      'select',
      {
        id: ids.target,
        name: 'target',
        class: 'input',
        autofocus: true,
        'aria-describedby': ids.summary,
      },
      choices.map(({ id, label }) => h('option', { value: id }, label)),
    );
    const summary = h('p', { id: ids.summary, class: 'hint' });
    const form = h(
      'form',
      { method: 'dialog', class: 'dialog-body' },
      h('h2', { id: ids.title, class: 'dialog-title' }, t('Move selection')),
      h(
        'p',
        { class: 'dialog-text' },
        count > 1
          ? t('{selected}, in their current order.', {
              selected: tn('{count} selected page', '{count} selected pages', count),
            })
          : t('1 page selected.'),
      ),
      h('fieldset', { class: 'field' }, h('legend', {}, t('Place')), h('div', { class: 'segmented' }, sides)),
      h('div', { class: 'field' }, h('label', { for: ids.target }, t('the page')), target),
      summary,
      h(
        'div',
        { class: 'dialog-actions' },
        h('button', { type: 'submit', value: 'cancel', class: 'btn' }, t('Cancel')),
        h('button', { type: 'submit', value: 'move', class: 'btn btn-primary' }, icon('move'), t('Move')),
      ),
    );
    const dialog = h('dialog', { class: 'dialog', 'aria-labelledby': ids.title }, form);

    const describe = () => {
      const after = form.elements.side.value === 'after';
      const page = choices.find(({ id }) => id === target.value)?.name ?? '';
      if (count > 1) {
        summary.textContent = after
          ? t('The {count} pages will go after {page}.', { count, page })
          : t('The {count} pages will go before {page}.', { count, page });
      } else {
        summary.textContent = after
          ? t('The page will go after {page}.', { page })
          : t('The page will go before {page}.', { page });
      }
    };
    form.addEventListener('change', describe);
    describe();
    dialog.addEventListener(
      'close',
      () => {
        resolve(dialog.returnValue === 'move' ? { targetId: target.value, side: form.elements.side.value } : null);
      },
      { once: true },
    );
    openModal(dialog);
  });
}

/**
 * Creates the organizer. The document view feeds it with `update(doc)` and
 * provides:
 * - `save(pageIds)` and `reset()`: send the order (PUT / DELETE
 *   /api/documents/{id}/order), show the returned document (which calls
 *   `update`), and resolve once done;
 * - `reload()`: fetch the document again (after a 409);
 * - `onDone()`: leave the organize mode.
 */
export function createPageOrganizer({ save, reset, reload, onDone }) {
  let latest = null; // last document received from the server
  let pages = new Map(); // id → page, from `latest`
  let order = []; // ids on screen, in order: may hold moves not sent yet
  let selected = new Set();
  let anchor = null; // where Shift ranges start: the last page clicked without Shift
  let dirty = false; // `order` has moves not sent yet
  let saving = false;
  let resetting = false;
  let gesture = null; // a press on a card, maybe a drag
  let ignoreClickUntil = 0;
  let announceTimer = 0;
  let destroyed = false;
  const savedWaiters = [];
  const cards = new Map(); // id → elements of its card

  const titleId = uniqueId('organizer-title');
  const title = h('h3', { id: titleId, class: 'organizer-title', tabindex: '-1' }, t('Organize pages'));
  const status = h('p', { class: 'organizer-status' });
  const savingNote = h(
    'p',
    { class: 'organizer-saving', hidden: true },
    h('span', { class: 'spinner', 'aria-hidden': 'true' }),
    t('Saving…'),
  );
  const clearButton = h(
    'button',
    { type: 'button', class: 'btn btn-small btn-compact' },
    icon('x'),
    h('span', { class: 'btn-label' }, t('Deselect all')),
  );
  const spanLong = h('span', { class: 'label-long' });
  const spanShort = h('span', { class: 'label-short' });
  const spanButton = h('button', { type: 'button', class: 'btn btn-small', hidden: true }, spanLong, spanShort);
  const moveButton = h(
    'button',
    { type: 'button', class: 'btn btn-small' },
    icon('move'),
    h('span', { class: 'label-long' }, t('Move selection…')),
    h('span', { class: 'label-short' }, t('Move…')),
  );
  const doneButton = h('button', { type: 'button', class: 'btn btn-primary btn-small' }, icon('check'), t('Done'));
  const resetButton = h(
    'button',
    { type: 'button', class: 'btn btn-small', hidden: true },
    icon('undo'),
    t('Restore automatic order'),
  );
  const toolbar = h(
    'div',
    { class: 'organizer-toolbar' },
    h('div', { class: 'organizer-heading' }, title, status, savingNote),
    h('div', { class: 'organizer-actions' }, clearButton, spanButton, moveButton, doneButton),
  );

  const outsideNote = h('p', { class: 'hint', hidden: true });
  const intro = h(
    'div',
    { class: 'organizer-intro' },
    h(
      'div',
      { class: 'organizer-help' },
      h(
        'p',
        { class: 'hint hint-fine-pointer' },
        t(
          'Drag a page to move it: if it is selected, the whole selection follows it. ' +
            'Click: select, Shift+click: range, Ctrl+click: add or remove. Esc cancels a move.',
        ),
      ),
      h(
        'p',
        { class: 'hint hint-coarse-pointer' },
        t(
          'Tap a page to select it, check others, then drag it by the handle ' +
            '(top right of the thumbnail) or after a long press.',
        ),
      ),
      outsideNote,
    ),
    resetButton,
  );

  function pageGroup() {
    const heading = h('h4', { class: 'page-group-title' });
    const hint = h('p', { class: 'page-group-hint' });
    const list = h('ol', { class: 'page-grid organizer-grid', role: 'list' });
    const element = h(
      'section',
      { class: 'organizer-group' },
      h('div', { class: 'page-group-header' }, heading, hint),
      list,
    );
    return { element, heading, hint, list };
  }
  const main = pageGroup();
  const tail = pageGroup();
  const indicator = h('span', { class: 'drop-indicator', hidden: true, 'aria-hidden': 'true' });
  const lists = h('div', { class: 'organizer-lists' }, main.element, tail.element, indicator);
  const announcer = h('p', { class: 'visually-hidden', 'aria-live': 'polite' });
  const element = h('section', { class: 'organizer', 'aria-labelledby': titleId }, toolbar, intro, lists, announcer);

  // The toolbar sticks under the sticky app header; cards scrolled into view stay clear of both.
  const header = document.getElementById('app-header');
  const resizeObserver = new ResizeObserver(() => {
    const headerHeight = header && !header.hidden ? header.offsetHeight : 0;
    element.style.setProperty('--organizer-top', `${headerHeight}px`);
    element.style.setProperty('--organizer-covered', `${headerHeight + toolbar.offsetHeight}px`);
  });
  if (header) resizeObserver.observe(header);
  resizeObserver.observe(toolbar);

  // --- rendering -------------------------------------------------------------

  /** The card of a page, created once and updated in place (so that it keeps the focus). */
  function cardOf(page) {
    const cached = cards.get(page.id);
    if (cached) return cached;
    const image = h('img', { alt: '', loading: 'lazy', decoding: 'async', draggable: 'false' });
    const label = h('span', { class: 'page-card-label' });
    const body = h('span', { class: 'page-card-body' }, label);
    const index = h('span', { class: 'organizer-index', 'aria-hidden': 'true' });
    const checkbox = h('input', { type: 'checkbox', name: 'selected-pages', value: page.id });
    const earlier = h(
      'button',
      {
        type: 'button',
        class: 'btn btn-icon btn-small',
        title: t('Place before the previous one'),
        dataset: { step: '-1' },
      },
      icon('chevron-left'),
    );
    const later = h(
      'button',
      {
        type: 'button',
        class: 'btn btn-icon btn-small',
        title: t('Place after the next one'),
        dataset: { step: '1' },
      },
      icon('chevron-right'),
    );
    const node = h(
      'li',
      { class: 'organizer-card', dataset: { id: page.id } },
      h(
        'div',
        { class: 'organizer-card-frame' },
        h(
          'span',
          { class: 'page-thumb' },
          image,
          index,
          h('span', { class: 'drag-handle', title: t('Drag to move'), 'aria-hidden': 'true' }, icon('grip')),
          h('label', { class: 'organizer-check' }, checkbox),
        ),
        body,
        h('span', { class: 'organizer-steps' }, earlier, later),
      ),
    );
    const card = { node, image, label, body, badge: null, place: null, index, checkbox, earlier, later };
    cards.set(page.id, card);
    return card;
  }

  function renderCard(card, page, position, withUnplaced) {
    // The server re-renders the thumbnail of a rotated page under the same URL.
    const src = versionedUrl(page.thumb_url, page.rotation ?? 0);
    if (card.image.getAttribute('src') !== src) card.image.src = src;
    const label = pageShortLabel(page);
    if (card.label.textContent !== label) card.label.textContent = label;
    const badge = `${page.placement}/${withUnplaced}`;
    if (card.badge !== badge) {
      card.badge = badge;
      setChildren(card.body, card.label, placementChip(page, withUnplaced));
    }
    // Refreshes come every few seconds while pages are being OCRed: only touch what changed.
    const place = `${position}/${order.length}/${page.page_label}/${resetting}`;
    if (card.place !== place) {
      card.place = place;
      const name = pageName(page, position);
      card.index.textContent = String(position + 1);
      card.checkbox.setAttribute('aria-label', t('Select {page}', { page: name }));
      card.earlier.setAttribute('aria-label', t('Place {page} before the previous one', { page: name }));
      card.later.setAttribute('aria-label', t('Place {page} after the next one', { page: name }));
      setUnavailable(card.earlier, position === 0 || resetting);
      setUnavailable(card.later, position === order.length - 1 || resetting);
    }
    renderCardSelection(card, page.id);
  }

  function renderCardSelection(card, id) {
    const isSelected = selected.has(id);
    card.node.classList.toggle('is-selected', isSelected);
    card.checkbox.checked = isSelected;
  }

  /** Moving nodes in the DOM takes the focus away from them: give it back. */
  function keepingFocus(update) {
    const focused = document.activeElement;
    update();
    if (focused instanceof HTMLElement && focused !== document.activeElement && focused.isConnected) {
      focused.focus({ preventScroll: true });
    }
  }

  function render() {
    // Unplaced pages close the reading order: they form the "Unnumbered pages"
    // group, unless no page has a place at all (the order is then the capture order).
    const unplaced = (id) => pages.get(id)?.placement === 'unplaced';
    const anyPlaced = order.some((id) => !unplaced(id));
    let split = order.length;
    if (anyPlaced) while (split > 0 && unplaced(order[split - 1])) split -= 1;

    const nodes = order.map((id, position) => {
      const page = pages.get(id);
      const card = cardOf(page);
      renderCard(card, page, position, anyPlaced);
      return card.node;
    });
    keepingFocus(() => {
      syncChildren(main.list, nodes.slice(0, split));
      syncChildren(tail.list, nodes.slice(split));
    });
    const shown = new Set(order);
    for (const id of cards.keys()) if (!shown.has(id)) cards.delete(id);

    main.heading.textContent = t('Reading order ({count})', { count: split });
    if (!order.length) main.hint.textContent = t('No page is in the document yet.');
    else if (anyPlaced) main.hint.textContent = t('The order of document.md.');
    else main.hint.textContent = t('No numbered page: capture order.');
    tail.element.hidden = split === order.length;
    tail.heading.textContent = t('Unnumbered pages ({count})', { count: order.length - split });
    tail.hint.textContent = t(
      'Nothing tells where they go: they are at the end of the document. ' + 'Drag them to their place.',
    );

    const outside = latest ? latest.pages.length - order.length : 0;
    outsideNote.hidden = outside === 0;
    outsideNote.textContent = tn(
      '{count} page is outside the document (waiting for OCR, failed, excluded or duplicate): ' + 'it is not affected.',
      '{count} pages are outside the document (waiting for OCR, failed, excluded or duplicates): ' +
        'they are not affected.',
      outside,
      { count: outside },
    );
    renderToolbar();
  }

  function renderToolbar() {
    const count = selected.size;
    status.textContent = count
      ? tn('{count} page selected out of {total}', '{count} pages selected out of {total}', count, {
          total: order.length,
        })
      : t('No page selected');
    setUnavailable(clearButton, count === 0);
    setUnavailable(moveButton, count === 0 || count === order.length || resetting);
    const span = spanOf(order, selected);
    spanButton.hidden = span.length <= count;
    spanLong.textContent = tn('Select the range ({count} page)', 'Select the range ({count} pages)', span.length);
    spanShort.textContent = t('Range ({count})', { count: span.length });
    const positioned = latest?.pages.some((page) => isPresent(page.position));
    resetButton.hidden = !(positioned || dirty || saving);
    setUnavailable(resetButton, saving || dirty || resetting);
    savingNote.hidden = !(saving || dirty || resetting);
    element.classList.toggle('is-busy', resetting);
    if (resetting) element.setAttribute('aria-busy', 'true');
    else element.removeAttribute('aria-busy');
  }

  function renderSelection() {
    for (const [id, card] of cards) renderCardSelection(card, id);
    renderToolbar();
  }

  /** Shows the last document received: its reading order replaces the order on screen. */
  function showLatest() {
    if (!latest || destroyed) return;
    pages = new Map(latest.pages.map((page) => [page.id, page]));
    order = latest.pages.filter((page) => page.in_document).map((page) => page.id);
    const present = new Set(order);
    selected = new Set([...selected].filter((id) => present.has(id)));
    if (!present.has(anchor)) anchor = null;
    render();
  }

  /** The server's version is shown when nothing is being dragged or sent. */
  function showLatestWhenIdle() {
    if (!gesture && !saving && !dirty && !resetting) showLatest();
  }

  function announce(message) {
    // Emptied first, so that the same message twice is read twice.
    announcer.textContent = '';
    clearTimeout(announceTimer);
    announceTimer = setTimeout(() => {
      announcer.textContent = message;
    }, 60);
  }

  function highlight(ids) {
    for (const id of ids) {
      const node = cards.get(id)?.node;
      if (!node) continue;
      node.classList.remove('is-moved');
      void node.offsetWidth; // restarts the animation
      node.classList.add('is-moved');
    }
  }

  function describeMove(moved) {
    const positions = moved.map((id) => order.indexOf(id) + 1);
    if (moved.length === 1) {
      return t('{page}: position {position} of {total}.', {
        page: pageTitle(pages.get(moved[0])),
        position: positions[0],
        total: order.length,
      });
    }
    return t('{count} pages moved: positions {first} to {last} of {total}.', {
      count: moved.length,
      first: positions[0],
      last: positions.at(-1),
      total: order.length,
    });
  }

  // --- changes and saving ------------------------------------------------------

  /** Shows a new order at once and sends it. */
  function change(next, moved) {
    order = next;
    dirty = true;
    render();
    highlight(moved);
    announce(describeMove(moved));
    flush();
  }

  /** Sends the order on screen; one request at a time, the last order wins. */
  async function flush() {
    if (saving || resetting || !dirty) return;
    saving = true;
    dirty = false;
    renderToolbar();
    let failure = null;
    try {
      await save(order.slice());
    } catch (error) {
      failure = error;
    }
    saving = false;
    if (failure) {
      dirty = false; // moves made meanwhile were based on the refused order
      if (failure instanceof ApiError && failure.status === 409) {
        toast(conflictMessage(), { tone: 'error' });
        reload();
      } else {
        toast(errorMessage(failure, t('The new order could not be saved.')), { tone: 'error' });
      }
    } else if (dirty) {
      flush();
      return;
    }
    showLatestWhenIdle(); // after a failure: back to the last order known from the server
    renderToolbar();
    for (const resolve of savedWaiters.splice(0)) resolve();
  }

  function whenSaved() {
    return saving || dirty ? new Promise((resolve) => savedWaiters.push(resolve)) : Promise.resolve();
  }

  // --- selection ---------------------------------------------------------------

  /** Plain click: this page only; `toggle` (Ctrl/Cmd, checkbox): add or remove it; `range` (Shift): from the anchor. */
  function select(id, { toggle = false, range = false } = {}) {
    if (range && anchor) {
      const ids = rangeOf(order, anchor, id);
      selected = toggle ? new Set([...selected, ...ids]) : new Set(ids);
    } else if (toggle) {
      if (selected.has(id)) selected.delete(id);
      else selected.add(id);
      anchor = id;
    } else {
      selected = new Set([id]);
      anchor = id;
    }
    renderSelection();
  }

  function clearSelection() {
    selected = new Set();
    anchor = null;
    renderSelection();
  }

  // --- moves with the buttons and the dialog -----------------------------------

  function moveOne(id, step, button) {
    const next = moveByOne(order, id, step);
    if (sameOrder(next, order)) return;
    change(next, [id]);
    // The button moved with its card and kept the focus: keep it in view.
    button.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }

  async function moveSelection() {
    const moving = inOrder(order, selected);
    if (!moving.length || moving.length === order.length || resetting) return;
    const movingSet = new Set(moving);
    const choices = order
      .map((id, position) => {
        const page = pages.get(id);
        return { id, label: `${position + 1} · ${pageShortLabel(page)}`, name: pageName(page, position) };
      })
      .filter(({ id }) => !movingSet.has(id));
    const choice = await moveDialog({ count: moving.length, choices });
    if (!choice || destroyed) return;
    // The list may have been refreshed while the dialog was open.
    const stillMoving = inOrder(order, moving);
    if (!order.includes(choice.targetId) || stillMoving.length !== moving.length) {
      toast(conflictMessage(), { tone: 'error' });
      return;
    }
    const next = moveNextTo(order, stillMoving, choice.targetId, choice.side);
    if (sameOrder(next, order)) {
      announce(t('The pages are already at this place.'));
      return;
    }
    change(next, stillMoving);
    cards.get(stillMoving[0])?.node.scrollIntoView({ block: 'nearest' });
  }

  async function resetOrder() {
    if (isUnavailable(resetButton)) return;
    const confirmed = await confirmDialog({
      title: t('Restore automatic order?'),
      message: t(
        'The pages will go back to the place given by their number or by their photo series. ' +
          'Moves made by hand will be forgotten.',
      ),
      confirmLabel: t('Restore automatic order'),
    });
    if (!confirmed || destroyed) return;
    await whenSaved();
    resetting = true;
    render();
    try {
      await reset();
      toast(t('Automatic order restored.'), { tone: 'success' });
    } catch (error) {
      toast(errorMessage(error, t('The automatic order could not be restored.')), { tone: 'error' });
    } finally {
      resetting = false;
      showLatest();
    }
    // The button disappears with the last manual place: keep the focus in the organizer.
    if (resetButton.hidden && (document.activeElement === resetButton || document.activeElement === document.body)) {
      title.focus();
    }
  }

  // --- dragging with Pointer Events --------------------------------------------

  function onPointerDown(event) {
    if (gesture || resetting || !event.isPrimary) return;
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    const card = event.target.closest('.organizer-card');
    if (!card) return;
    const onHandle = Boolean(event.target.closest('.drag-handle'));
    if (!onHandle && event.target.closest('input, label, button')) return;
    const mouse = event.pointerType === 'mouse';
    ignoreClickUntil = 0; // a new press: the click of an earlier drag can no longer come
    gesture = {
      pointerId: event.pointerId,
      pointerType: event.pointerType,
      card,
      id: card.dataset.id,
      startX: event.clientX,
      startY: event.clientY,
      x: event.clientX,
      y: event.clientY,
      // A mouse, or the grip handle, drags at once; elsewhere a finger scrolls the page unless it holds still.
      armed: mouse || onHandle,
      longPress: false,
      dragging: false,
      timer: 0,
      frame: 0,
      moving: [],
      target: null,
    };
    if (mouse)
      event.preventDefault(); // no text selection, no native image drag
    else if (!onHandle) gesture.timer = setTimeout(pickUp, LONG_PRESS_MS);
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerCancel);
  }

  /** Long press: the card is picked up and follows the finger from now on. */
  function pickUp() {
    if (!gesture || gesture.dragging) return;
    gesture.armed = true;
    gesture.longPress = true;
    gesture.card.classList.add('is-pressed');
  }

  function onPointerMove(event) {
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    gesture.x = event.clientX;
    gesture.y = event.clientY;
    if (!gesture.dragging) {
      const distance = Math.hypot(gesture.x - gesture.startX, gesture.y - gesture.startY);
      if (!gesture.armed) {
        if (distance > SCROLL_SLOP_PX) cancelGesture(); // the finger is scrolling the page
        return;
      }
      if (distance < (gesture.longPress ? 1 : DRAG_THRESHOLD_PX)) return;
      startDrag();
    }
    updateDrag();
  }

  function startDrag() {
    const g = gesture;
    g.dragging = true;
    clearTimeout(g.timer);
    g.moving = selected.has(g.id) ? inOrder(order, selected) : [g.id];
    for (const id of g.moving) cards.get(id)?.node.classList.add('is-dragging');
    g.card.classList.remove('is-pressed');
    element.classList.add('is-dragging');
    document.body.classList.add('is-dragging-pages');
    g.ghost = dragGhost(g.card, g.moving.length);
    document.body.append(g.ghost);
    g.ghostSize = { width: g.ghost.offsetWidth, height: g.ghost.offsetHeight };
    try {
      g.card.setPointerCapture(g.pointerId);
    } catch {
      // The pointer is already gone: pointerup or pointercancel ends the gesture.
    }
    measure();
    document.addEventListener('keydown', onDragKey, true);
    window.addEventListener('scroll', onDragScroll, { passive: true });
    window.addEventListener('resize', onDragResize);
    window.addEventListener('blur', cancelGesture);
    g.frame = requestAnimationFrame(tick);
  }

  function listsBox() {
    const box = lists.getBoundingClientRect();
    return { left: box.left + window.scrollX, top: box.top + window.scrollY, width: box.width, height: box.height };
  }

  /** Card boxes in document coordinates: they stay valid while the page scrolls. */
  function measure() {
    const g = gesture;
    const { scrollX, scrollY } = window;
    g.rects = order.map((id) => {
      const box = cards.get(id).node.getBoundingClientRect();
      return {
        left: box.left + scrollX,
        top: box.top + scrollY,
        right: box.right + scrollX,
        bottom: box.bottom + scrollY,
      };
    });
    g.gap = columnGap(g.rects);
    g.origin = listsBox();
  }

  function updateDrag() {
    const g = gesture;
    const mouse = g.pointerType === 'mouse';
    const ghostX = mouse ? g.x + GHOST_MOUSE_OFFSET_PX : g.x - g.ghostSize.width / 2;
    const ghostY = mouse ? g.y + GHOST_MOUSE_OFFSET_PX : g.y - g.ghostSize.height - GHOST_FINGER_GAP_PX;
    g.ghost.style.transform = `translate(${ghostX}px, ${ghostY}px)`;

    g.target = dropTarget(g.rects, g.x + window.scrollX, g.y + window.scrollY);
    indicator.hidden = !g.target;
    if (!g.target) return;
    const mark = insertionMark(g.rects, g.target, g.gap);
    indicator.style.transform = `translate(${mark.x - g.origin.left}px, ${mark.top - g.origin.top}px)`;
    indicator.style.height = `${mark.bottom - mark.top}px`;
  }

  /** Bottom of what covers the top of the viewport: the app header, and the toolbar once it sticks. */
  function coveredTop() {
    const headerBottom = header && !header.hidden ? header.getBoundingClientRect().bottom : 0;
    const bar = toolbar.getBoundingClientRect();
    return bar.top <= headerBottom + 1 ? Math.max(headerBottom, bar.bottom) : headerBottom;
  }

  /** Every frame of a drag: follow layout changes, scroll near the edges of the viewport. */
  function tick() {
    const g = gesture;
    if (!g?.dragging) return;
    const box = listsBox();
    if (['left', 'top', 'width', 'height'].some((key) => Math.abs(box[key] - g.origin[key]) > LAYOUT_TOLERANCE_PX)) {
      measure();
      updateDrag();
    }
    const step = autoScrollStep(g.y, coveredTop(), window.innerHeight);
    if (step) window.scrollBy(0, step); // the scroll event moves the drop target
    g.frame = requestAnimationFrame(tick);
  }

  function onDragScroll() {
    if (gesture?.dragging) updateDrag();
  }

  function onDragResize() {
    if (!gesture?.dragging) return;
    measure();
    updateDrag();
  }

  function onDragKey(event) {
    if (event.key !== 'Escape') return;
    event.preventDefault();
    event.stopPropagation();
    ignoreNextClick(); // the mouse button is still down: its click must not select
    cancelGesture();
    announce(t('Move canceled.'));
  }

  function ignoreNextClick() {
    ignoreClickUntil = performance.now() + CLICK_AFTER_DRAG_MS;
  }

  function onPointerUp(event) {
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    const g = gesture;
    if (g.dragging) {
      ignoreNextClick();
      const next = g.target ? moveBlock(order, g.moving, g.target.index) : order;
      endGesture();
      if (!sameOrder(next, order)) change(next, g.moving);
      else showLatestWhenIdle();
      return;
    }
    endGesture();
    if (g.longPress) {
      // Held still, then released: a tap.
      ignoreNextClick();
      select(g.id);
    } // otherwise the click that follows selects
    showLatestWhenIdle();
  }

  function onPointerCancel(event) {
    if (gesture && event.pointerId === gesture.pointerId) cancelGesture();
  }

  function cancelGesture() {
    if (!gesture) return;
    endGesture();
    showLatestWhenIdle();
  }

  function endGesture() {
    const g = gesture;
    if (!g) return;
    gesture = null;
    clearTimeout(g.timer);
    cancelAnimationFrame(g.frame);
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup', onPointerUp);
    window.removeEventListener('pointercancel', onPointerCancel);
    document.removeEventListener('keydown', onDragKey, true);
    window.removeEventListener('scroll', onDragScroll);
    window.removeEventListener('resize', onDragResize);
    window.removeEventListener('blur', cancelGesture);
    g.card.classList.remove('is-pressed');
    for (const id of g.moving) cards.get(id)?.node.classList.remove('is-dragging');
    g.ghost?.remove();
    indicator.hidden = true;
    element.classList.remove('is-dragging');
    document.body.classList.remove('is-dragging-pages');
    if (g.dragging && g.card.hasPointerCapture(g.pointerId)) g.card.releasePointerCapture(g.pointerId);
  }

  // --- events ------------------------------------------------------------------

  lists.addEventListener('pointerdown', onPointerDown);
  // A finger that picked a card up must not scroll the page (touch-action is
  // decided when the finger lands, before the long press).
  lists.addEventListener(
    'touchmove',
    (event) => {
      if (gesture?.armed && event.cancelable) event.preventDefault();
    },
    { passive: false },
  );
  lists.addEventListener('contextmenu', (event) => {
    if (gesture && gesture.pointerType !== 'mouse') event.preventDefault(); // long-press menu
  });
  lists.addEventListener('dragstart', (event) => event.preventDefault());
  lists.addEventListener('click', (event) => {
    const card = event.target.closest('.organizer-card');
    if (!card) return;
    if (performance.now() < ignoreClickUntil) {
      ignoreClickUntil = 0;
      event.preventDefault(); // also leaves a checkbox under the pointer as it was
      return;
    }
    const { id } = card.dataset;
    const stepButton = event.target.closest('button[data-step]');
    if (stepButton) {
      if (!isUnavailable(stepButton)) moveOne(id, Number(stepButton.dataset.step), stepButton);
    } else if (event.target.matches('input[type="checkbox"]')) {
      select(id, { toggle: true, range: event.shiftKey });
    } else if (!event.target.closest('label')) {
      // a label forwards its click to its checkbox
      select(id, { range: event.shiftKey, toggle: event.ctrlKey || event.metaKey });
    }
  });
  // Escape empties the selection (a mouse click on a card does not move the focus into the organizer).
  function onEscape(event) {
    if (event.key !== 'Escape' || event.defaultPrevented || gesture || !selected.size) return;
    if (document.querySelector('dialog[open]')) return;
    event.preventDefault();
    clearSelection();
    announce(t('No page selected anymore.'));
  }
  document.addEventListener('keydown', onEscape);
  clearButton.addEventListener('click', () => {
    if (!isUnavailable(clearButton)) clearSelection();
  });
  spanButton.addEventListener('click', () => {
    selected = new Set(spanOf(order, selected));
    renderSelection();
    moveButton.focus(); // this button is gone now that the range is full; moving it is the next step
  });
  moveButton.addEventListener('click', () => {
    if (!isUnavailable(moveButton)) moveSelection();
  });
  resetButton.addEventListener('click', resetOrder);
  doneButton.addEventListener('click', () => onDone());

  return {
    element,
    /** Shows a newer document (a refresh, or the answer to an order change). */
    update(doc) {
      latest = doc;
      showLatestWhenIdle();
    },
    focus() {
      title.focus();
    },
    destroy() {
      destroyed = true;
      endGesture();
      document.removeEventListener('keydown', onEscape);
      clearTimeout(announceTimer);
      resizeObserver.disconnect();
    },
  };
}
