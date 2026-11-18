import type { PageId, ReadingOrder } from '../../../domain/reading-order.ts';
import {
  CLICK_AFTER_DRAG_MILLISECONDS,
  coveredTopPixels,
  type Gesture,
  type GestureOutcome,
  ghostPosition,
  hasLayoutMoved,
  isMouse,
  LONG_PRESS_MILLISECONDS,
  moveGesture,
  type PixelBox,
  type PixelSize,
  pickUpGesture,
  pressGesture,
  releaseGesture,
  startDragging,
} from './drag-gesture.ts';
import {
  autoScrollStep,
  columnGap,
  type DropTarget,
  dropTarget,
  insertionMark,
  type PixelRectangle,
} from './grid-geometry.ts';

export interface PageDragElements {
  readonly organizer: HTMLElement;
  readonly toolbar: HTMLElement;
  readonly lists: HTMLElement;
  readonly indicator: HTMLElement;
}

export interface PageDragCallbacks {
  readonly isResetting: () => boolean;
  readonly order: () => ReadingOrder;
  readonly selected: () => ReadonlySet<PageId>;
  readonly cardOf: (pageId: PageId) => HTMLElement | undefined;
  readonly onGestureStart: () => void;
  readonly onGestureEnd: (outcome: GestureOutcome) => void;
}

export interface PageDrag {
  takeIgnoredClick(): boolean;
  destroy(): void;
}

interface DragScene {
  readonly ghost: HTMLElement;
  readonly ghostSize: PixelSize;
  rectangles: PixelRectangle[];
  gapPixels: number;
  origin: PixelBox;
  target: DropTarget | null;
}

interface ActivePress {
  gesture: Gesture;
  readonly card: HTMLElement;
  longPressTimer: number;
  frame: number;
  scene: DragScene | null;
}

const ESCAPE = 'Escape';
const APP_HEADER_ID = 'app-header';

function closestElement(target: EventTarget | null, selector: string): Element | null {
  return target instanceof Element ? target.closest(selector) : null;
}

function documentBox(element: Element): PixelBox {
  const box = element.getBoundingClientRect();
  return { left: box.left + window.scrollX, top: box.top + window.scrollY, width: box.width, height: box.height };
}

function dragGhost(card: HTMLElement, count: number): HTMLElement {
  const ghost = document.createElement('div');
  ghost.className = 'drag-ghost';
  ghost.setAttribute('aria-hidden', 'true');
  const image = card.querySelector('.page-thumb img');
  if (image instanceof HTMLImageElement) {
    const copy = document.createElement('img');
    copy.src = image.currentSrc || image.src;
    copy.alt = '';
    copy.draggable = false;
    ghost.append(copy);
  }
  if (count > 1) {
    const badge = document.createElement('span');
    badge.className = 'drag-ghost-count';
    badge.textContent = String(count);
    ghost.append(badge);
  }
  return ghost;
}

// Drags cards with Pointer Events, which work with a mouse, a finger and a pen, where the HTML drag and drop API does
// not work on touch screens. The moving cards, the dragged thumbnail and the drop indicator change through the DOM
// while the pointer moves, so that the screen draws again only when the drop changes the order.
export function createPageDrag(elements: PageDragElements, callbacks: PageDragCallbacks): PageDrag {
  const { organizer, toolbar, lists, indicator } = elements;
  let press: ActivePress | null = null;
  let ignoreClickUntilMilliseconds = 0;

  function ignoreNextClick(): void {
    ignoreClickUntilMilliseconds = performance.now() + CLICK_AFTER_DRAG_MILLISECONDS;
  }

  function appHeader(): HTMLElement | null {
    const header = document.getElementById(APP_HEADER_ID);
    return header !== null && !header.hidden ? header : null;
  }

  function measure(current: ActivePress, scene: DragScene): void {
    const { scrollX, scrollY } = window;
    scene.rectangles = callbacks.order().map((pageId) => {
      const box = callbacks.cardOf(pageId)?.getBoundingClientRect();
      if (box === undefined) throw new RangeError(`No card for the page ${pageId}`);
      return {
        left: box.left + scrollX,
        top: box.top + scrollY,
        right: box.right + scrollX,
        bottom: box.bottom + scrollY,
      };
    });
    scene.gapPixels = columnGap(scene.rectangles);
    scene.origin = documentBox(lists);
    follow(current, scene);
  }

  function follow(current: ActivePress, scene: DragScene): void {
    const { gesture } = current;
    const pointer = gesture.pointerPixels;
    const ghostAt = ghostPosition(gesture.pointerType, pointer, scene.ghostSize);
    scene.ghost.style.transform = `translate(${ghostAt.x}px, ${ghostAt.y}px)`;
    scene.target = dropTarget(scene.rectangles, { x: pointer.x + window.scrollX, y: pointer.y + window.scrollY });
    indicator.hidden = scene.target === null;
    if (scene.target === null) return;
    const mark = insertionMark(scene.rectangles, scene.target, scene.gapPixels);
    indicator.style.transform = `translate(${mark.x - scene.origin.left}px, ${mark.top - scene.origin.top}px)`;
    indicator.style.height = `${mark.bottom - mark.top}px`;
  }

  function coveredTop(): number {
    const header = appHeader();
    const bar = toolbar.getBoundingClientRect();
    return coveredTopPixels(header === null ? 0 : header.getBoundingClientRect().bottom, bar.top, bar.bottom);
  }

  function tick(): void {
    const current = press;
    const scene = current?.scene;
    if (current === null || scene === null || scene === undefined) return;
    if (hasLayoutMoved(documentBox(lists), scene.origin)) measure(current, scene);
    const stepPixels = autoScrollStep(current.gesture.pointerPixels.y, coveredTop(), window.innerHeight);
    // The scroll event moves the drop target.
    if (stepPixels !== 0) window.scrollBy(0, stepPixels);
    current.frame = requestAnimationFrame(tick);
  }

  function startDrag(current: ActivePress): void {
    current.gesture = startDragging(current.gesture, callbacks.order(), callbacks.selected());
    window.clearTimeout(current.longPressTimer);
    for (const pageId of current.gesture.moving) callbacks.cardOf(pageId)?.classList.add('is-dragging');
    current.card.classList.remove('is-pressed');
    organizer.classList.add('is-dragging');
    document.body.classList.add('is-dragging-pages');
    const ghost = dragGhost(current.card, current.gesture.moving.length);
    document.body.append(ghost);
    const scene: DragScene = {
      ghost,
      ghostSize: { width: ghost.offsetWidth, height: ghost.offsetHeight },
      rectangles: [],
      gapPixels: 0,
      origin: documentBox(lists),
      target: null,
    };
    current.scene = scene;
    try {
      current.card.setPointerCapture(current.gesture.pointerId);
    } catch {
      // The pointer is already gone: its pointerup or pointercancel ends the gesture.
    }
    measure(current, scene);
    document.addEventListener('keydown', onDragKey, true);
    window.addEventListener('scroll', onDragScroll, { passive: true });
    window.addEventListener('resize', onDragResize);
    window.addEventListener('blur', onBlur);
    current.frame = requestAnimationFrame(tick);
  }

  function endPress(): ActivePress | null {
    const ended = press;
    if (ended === null) return null;
    press = null;
    window.clearTimeout(ended.longPressTimer);
    cancelAnimationFrame(ended.frame);
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup', onPointerUp);
    window.removeEventListener('pointercancel', onPointerCancel);
    document.removeEventListener('keydown', onDragKey, true);
    window.removeEventListener('scroll', onDragScroll);
    window.removeEventListener('resize', onDragResize);
    window.removeEventListener('blur', onBlur);
    ended.card.classList.remove('is-pressed');
    for (const pageId of ended.gesture.moving) callbacks.cardOf(pageId)?.classList.remove('is-dragging');
    ended.scene?.ghost.remove();
    indicator.hidden = true;
    organizer.classList.remove('is-dragging');
    document.body.classList.remove('is-dragging-pages');
    if (ended.gesture.isDragging && ended.card.hasPointerCapture(ended.gesture.pointerId)) {
      ended.card.releasePointerCapture(ended.gesture.pointerId);
    }
    return ended;
  }

  function cancel(isByKey: boolean): void {
    if (endPress() !== null) callbacks.onGestureEnd({ kind: 'cancel', isByKey });
  }

  function onPointerDown(event: PointerEvent): void {
    const card = closestElement(event.target, '.organizer-card');
    const pageId = card instanceof HTMLElement ? (card.dataset.id ?? null) : null;
    const start = pressGesture(
      {
        pointerId: event.pointerId,
        pointerType: event.pointerType,
        isPrimary: event.isPrimary,
        button: event.button,
        pointerPixels: { x: event.clientX, y: event.clientY },
        pageId,
        isOnHandle: closestElement(event.target, '.drag-handle') !== null,
        isOnControl: closestElement(event.target, 'input, label, button') !== null,
      },
      press !== null || callbacks.isResetting(),
    );
    if (start === null || !(card instanceof HTMLElement)) return;
    // A new press: the click of an earlier drag can no longer come.
    ignoreClickUntilMilliseconds = 0;
    press = { gesture: start.gesture, card, longPressTimer: 0, frame: 0, scene: null };
    callbacks.onGestureStart();
    if (start.preventsDefault) event.preventDefault();
    if (start.waitsForLongPress) press.longPressTimer = window.setTimeout(onLongPress, LONG_PRESS_MILLISECONDS);
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerCancel);
  }

  function onLongPress(): void {
    if (press === null || press.gesture.isDragging) return;
    press.gesture = pickUpGesture(press.gesture);
    press.card.classList.add('is-pressed');
  }

  function onPointerMove(event: PointerEvent): void {
    const current = press;
    if (current === null || event.pointerId !== current.gesture.pointerId) return;
    const { gesture, step } = moveGesture(current.gesture, { x: event.clientX, y: event.clientY });
    current.gesture = gesture;
    if (step === 'cancel') cancel(false);
    else if (step === 'start') startDrag(current);
    else if (step === 'follow' && current.scene !== null) follow(current, current.scene);
  }

  function onPointerUp(event: PointerEvent): void {
    const current = press;
    if (current === null || event.pointerId !== current.gesture.pointerId) return;
    const release = releaseGesture(current.gesture, current.scene?.target ?? null, callbacks.order());
    if (release.ignoresClick) ignoreNextClick();
    endPress();
    callbacks.onGestureEnd(release.outcome);
  }

  function onPointerCancel(event: PointerEvent): void {
    if (press !== null && event.pointerId === press.gesture.pointerId) cancel(false);
  }

  function onDragKey(event: KeyboardEvent): void {
    if (event.key !== ESCAPE) return;
    event.preventDefault();
    event.stopPropagation();
    // The mouse button is still down: its click must not select.
    ignoreNextClick();
    cancel(true);
  }

  function onDragScroll(): void {
    if (press?.scene) follow(press, press.scene);
  }

  function onDragResize(): void {
    if (press?.scene) measure(press, press.scene);
  }

  function onBlur(): void {
    cancel(false);
  }

  // A finger that picked a card up must not scroll the page: the browser decides touch-action when the finger lands,
  // before the long press.
  function onTouchMove(event: TouchEvent): void {
    if (press?.gesture.isArmed && event.cancelable) event.preventDefault();
  }

  // The menu of a long press.
  function onContextMenu(event: Event): void {
    if (press !== null && !isMouse(press.gesture.pointerType)) event.preventDefault();
  }

  function onDragStart(event: Event): void {
    event.preventDefault();
  }

  lists.addEventListener('pointerdown', onPointerDown);
  lists.addEventListener('touchmove', onTouchMove, { passive: false });
  lists.addEventListener('contextmenu', onContextMenu);
  lists.addEventListener('dragstart', onDragStart);

  return {
    takeIgnoredClick() {
      if (performance.now() >= ignoreClickUntilMilliseconds) return false;
      ignoreClickUntilMilliseconds = 0;
      return true;
    },
    destroy() {
      endPress();
      lists.removeEventListener('pointerdown', onPointerDown);
      lists.removeEventListener('touchmove', onTouchMove);
      lists.removeEventListener('contextmenu', onContextMenu);
      lists.removeEventListener('dragstart', onDragStart);
    },
  };
}
