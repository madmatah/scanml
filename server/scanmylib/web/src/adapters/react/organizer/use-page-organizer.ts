import {
  type RefCallback,
  type RefObject,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';
import { flushSync } from 'react-dom';
import { useTranslation } from 'react-i18next';

import {
  createOrganizerStore,
  type OrganizerPlacement,
  type OrganizerStore,
  type OrganizerToolbar,
  organizerToolbar,
} from '../../../application/organizer-store.ts';
import type { DocumentWithPages, PageSummary } from '../../../domain/document-details.ts';
import {
  inOrder,
  type PageId,
  type ReadingOrder,
  type ReadingOrderGroups,
  readingOrderGroups,
  sameOrder,
} from '../../../domain/reading-order.ts';
import type { Selection } from '../../../domain/selection.ts';
import type { Toasts } from '../shell/toasts.ts';
import type { GestureOutcome } from './drag-gesture.ts';
import { conflictText, type MoveChoice, moveChoices, moveText, organizerNotice } from './organizer-text.ts';
import { createPageDrag } from './page-drag.ts';
import type { MoveTarget } from './use-move-dialog.ts';

export interface PageOrganizerServices {
  readonly save: (order: ReadingOrder) => Promise<DocumentWithPages>;
  readonly reset: () => Promise<DocumentWithPages>;
  readonly reload: () => void;
  readonly toasts: Toasts;
}

export type OrganizerDialog =
  | { readonly kind: 'move'; readonly moving: readonly PageId[]; readonly choices: readonly MoveChoice[] }
  | { readonly kind: 'reset' }
  | null;

export interface PageOrganizerState {
  readonly organizer: RefObject<HTMLElement | null>;
  readonly toolbar: RefObject<HTMLDivElement | null>;
  readonly lists: RefObject<HTMLDivElement | null>;
  readonly indicator: RefObject<HTMLSpanElement | null>;
  readonly title: RefObject<HTMLHeadingElement | null>;
  readonly moveButton: RefObject<HTMLButtonElement | null>;
  readonly resetButton: RefObject<HTMLButtonElement | null>;
  readonly announcer: RefObject<HTMLParagraphElement | null>;
  readonly cardRef: (pageId: PageId) => RefCallback<HTMLLIElement>;
  readonly order: ReadingOrder;
  readonly pages: ReadonlyMap<PageId, PageSummary>;
  readonly selection: Selection;
  readonly isResetting: boolean;
  readonly toolbarState: OrganizerToolbar;
  readonly groups: ReadingOrderGroups;
  readonly outsideCount: number;
  readonly movedPageIds: ReadonlySet<PageId>;
  readonly openDialog: OrganizerDialog;
  readonly onClearSelection: () => void;
  readonly onSelectSpan: () => void;
  readonly onMoveSelection: () => void;
  readonly onRestoreOrder: () => void;
  readonly onMoveClosed: (moving: readonly PageId[], target: MoveTarget | null) => void;
  readonly onResetClosed: (isConfirmed: boolean) => void;
}

type CardNodes = Map<PageId, HTMLLIElement>;

const ESCAPE = 'Escape';
const APP_HEADER_ID = 'app-header';
// The live region is emptied first, so that the same message twice is read twice.
const ANNOUNCE_DELAY_MILLISECONDS = 60;
const BEFORE = -1;
const AFTER = 1;

const isUnavailable = (button: Element): boolean => {
  return button.getAttribute('aria-disabled') === 'true';
};

const closestElement = (target: EventTarget | null, selector: string): Element | null => {
  return target instanceof Element ? target.closest(selector) : null;
};

const highlight = (cards: CardNodes, moved: readonly PageId[]): void => {
  for (const pageId of moved) {
    const node = cards.get(pageId);
    if (node === undefined) continue;
    node.classList.remove('is-moved');
    void node.offsetWidth;
    node.classList.add('is-moved');
  }
};

export const usePageOrganizer = (
  document: DocumentWithPages,
  { save, reset, reload, toasts }: PageOrganizerServices,
): PageOrganizerState => {
  const { t } = useTranslation();
  const [store] = useState<OrganizerStore>(() =>
    createOrganizerStore(document, {
      save,
      reset,
      reload,
      report: (event) => {
        const notice = organizerNotice(t, event);
        toasts.show(notice.message, notice.tone);
      },
    }),
  );
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot);
  // A card keeps its mark once moved, so that its animation plays to its end whatever is drawn meanwhile.
  const [movedPageIds, setMovedPageIds] = useState<ReadonlySet<PageId>>(() => new Set());
  const [openDialog, setOpenDialog] = useState<OrganizerDialog>(null);
  const organizer = useRef<HTMLElement>(null);
  const toolbar = useRef<HTMLDivElement>(null);
  const lists = useRef<HTMLDivElement>(null);
  const indicator = useRef<HTMLSpanElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const moveButton = useRef<HTMLButtonElement>(null);
  const resetButton = useRef<HTMLButtonElement>(null);
  const announcer = useRef<HTMLParagraphElement>(null);
  const announceTimer = useRef(0);
  const cards = useRef<CardNodes>(new Map());
  // One callback per page for the organizer's whole life, so that a card's ref keeps its identity and its memo holds.
  const cardRefs = useRef(new Map<PageId, RefCallback<HTMLLIElement>>());
  const wasResetting = useRef(false);

  const announce = useCallback((message: string) => {
    const element = announcer.current;
    if (element === null) return;
    element.textContent = '';
    window.clearTimeout(announceTimer.current);
    announceTimer.current = window.setTimeout(() => {
      element.textContent = message;
    }, ANNOUNCE_DELAY_MILLISECONDS);
  }, []);

  // A move shows at once with its marks, so that its cards, drawn in their new order, can be highlighted and it can be
  // told.
  const applyMove = useCallback(
    (move: () => OrganizerPlacement): OrganizerPlacement => {
      const outcome = flushSync(() => {
        const done = move();
        if (done.kind === 'moved') setMovedPageIds((previous) => new Set([...previous, ...done.moved]));
        return done;
      });
      if (outcome.kind === 'moved') {
        highlight(cards.current, outcome.moved);
        const shown = store.getSnapshot();
        announce(moveText(t, shown.pages, shown.order, outcome.moved));
      }
      return outcome;
    },
    [store, t, announce],
  );

  const cardRef = useCallback((pageId: PageId): RefCallback<HTMLLIElement> => {
    const known = cardRefs.current.get(pageId);
    if (known !== undefined) return known;
    const nodes = cards.current;
    const register = (node: HTMLLIElement | null) => {
      if (node === null) return;
      nodes.set(pageId, node);
      return () => {
        if (nodes.get(pageId) === node) nodes.delete(pageId);
      };
    };
    cardRefs.current.set(pageId, register);
    return register;
  }, []);

  useEffect(() => {
    store.update(document);
  }, [store, document]);

  useLayoutEffect(() => {
    title.current?.focus();
  }, []);

  useEffect(() => () => window.clearTimeout(announceTimer.current), []);

  // The toolbar sticks under the sticky header of the app, and the cards scrolled into view stay clear of both.
  useEffect(() => {
    const section = organizer.current;
    const bar = toolbar.current;
    if (section === null || bar === null) return;
    const header = window.document.getElementById(APP_HEADER_ID);
    const observer = new ResizeObserver(() => {
      const headerHeight = header !== null && !header.hidden ? header.offsetHeight : 0;
      section.style.setProperty('--organizer-top', `${headerHeight}px`);
      section.style.setProperty('--organizer-covered', `${headerHeight + bar.offsetHeight}px`);
    });
    if (header !== null) observer.observe(header);
    observer.observe(bar);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const section = organizer.current;
    const bar = toolbar.current;
    const listsElement = lists.current;
    const indicatorElement = indicator.current;
    if (section === null || bar === null || listsElement === null || indicatorElement === null) return;

    const endGesture = (outcome: GestureOutcome): void => {
      switch (outcome.kind) {
        case 'drop':
          if (!sameOrder(outcome.order, store.getSnapshot().order)) {
            applyMove(() => {
              store.change(outcome.order);
              return { kind: 'moved', moved: outcome.moving };
            });
          }
          break;
        case 'tap':
          store.select(outcome.pageId, { isToggle: false, isRange: false });
          break;
        case 'release':
          break;
        case 'cancel':
          if (outcome.isByKey) announce(t('Move canceled.'));
          break;
        default:
          throw new Error(`Unknown end of a gesture: ${JSON.stringify(outcome satisfies never)}`);
      }
      store.endGesture();
    };

    const drag = createPageDrag(
      { organizer: section, toolbar: bar, lists: listsElement, indicator: indicatorElement },
      {
        isResetting: () => store.getSnapshot().isResetting,
        order: () => store.getSnapshot().order,
        selected: () => store.getSnapshot().selection.selected,
        cardOf: (pageId) => cards.current.get(pageId),
        onGestureStart: () => store.beginGesture(),
        onGestureEnd: endGesture,
      },
    );

    const moveOne = (pageId: PageId, step: typeof BEFORE | typeof AFTER, button: HTMLElement): void => {
      if (applyMove(() => store.moveOne(pageId, step)).kind !== 'moved') return;
      // The button moved with its card and kept the focus: it stays in view.
      button.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    };

    const onClick = (event: MouseEvent): void => {
      const card = closestElement(event.target, '.organizer-card');
      if (!(card instanceof HTMLElement)) return;
      if (drag.takeIgnoredClick()) {
        // This also leaves a checkbox under the pointer as it was.
        event.preventDefault();
        return;
      }
      const pageId = card.dataset.id;
      if (pageId === undefined) return;
      const stepButton = closestElement(event.target, 'button[data-step]');
      if (stepButton instanceof HTMLElement) {
        if (!isUnavailable(stepButton)) moveOne(pageId, stepButton.dataset.step === '-1' ? BEFORE : AFTER, stepButton);
      } else if (event.target instanceof HTMLInputElement && event.target.type === 'checkbox') {
        store.select(pageId, { isToggle: true, isRange: event.shiftKey });
      } else if (closestElement(event.target, 'label') === null) {
        // A label passes its click on to its checkbox.
        store.select(pageId, { isToggle: event.ctrlKey || event.metaKey, isRange: event.shiftKey });
      }
    };

    // Escape empties the selection: a mouse click on a card does not move the focus into the organizer.
    const onEscape = (event: KeyboardEvent): void => {
      if (event.key !== ESCAPE || event.defaultPrevented || store.hasGesture()) return;
      if (store.getSnapshot().selection.selected.size === 0) return;
      if (window.document.querySelector('dialog[open]') !== null) return;
      event.preventDefault();
      store.clearSelection();
      announce(t('No page selected anymore.'));
    };

    listsElement.addEventListener('click', onClick);
    window.document.addEventListener('keydown', onEscape);
    return () => {
      drag.destroy();
      listsElement.removeEventListener('click', onClick);
      window.document.removeEventListener('keydown', onEscape);
    };
  }, [store, t, applyMove, announce]);

  // The button disappears with the last place chosen by hand: the focus stays in the organizer.
  useLayoutEffect(() => {
    const button = resetButton.current;
    const focused = window.document.activeElement;
    if (wasResetting.current && !snapshot.isResetting && button?.hidden === true) {
      if (focused === button || focused === window.document.body) title.current?.focus();
    }
    wasResetting.current = snapshot.isResetting;
  }, [snapshot.isResetting]);

  const { order, pages, selection, isResetting } = snapshot;

  return {
    organizer,
    toolbar,
    lists,
    indicator,
    title,
    moveButton,
    resetButton,
    announcer,
    cardRef,
    order,
    pages,
    selection,
    isResetting,
    toolbarState: organizerToolbar(snapshot),
    groups: readingOrderGroups(order, pages),
    outsideCount: snapshot.document.pages.length - order.length,
    movedPageIds,
    openDialog,
    onClearSelection: () => store.clearSelection(),
    onSelectSpan: () => {
      store.selectSpan();
      // This button goes now that the range is whole: moving it is the next step.
      moveButton.current?.focus();
    },
    onMoveSelection: () => {
      const moving = inOrder(order, selection.selected);
      if (moving.length === 0 || moving.length === order.length || isResetting) return;
      setOpenDialog({ kind: 'move', moving, choices: moveChoices(t, pages, order, moving) });
    },
    onRestoreOrder: () => setOpenDialog({ kind: 'reset' }),
    onMoveClosed: (moving, target) => {
      setOpenDialog(null);
      if (target === null) return;
      const placement = applyMove(() => store.place(moving, target.targetId, target.side));
      switch (placement.kind) {
        case 'conflict':
          toasts.show(conflictText(t), 'error');
          return;
        case 'unchanged':
          announce(t('The pages are already at this place.'));
          return;
        case 'moved': {
          const [first] = placement.moved;
          if (first !== undefined) cards.current.get(first)?.scrollIntoView({ block: 'nearest' });
          return;
        }
        default:
          throw new Error(`Unknown placement: ${JSON.stringify(placement satisfies never)}`);
      }
    },
    onResetClosed: (isConfirmed) => {
      setOpenDialog(null);
      // resetOrder tells its outcome through the store's report, so its promise never rejects.
      if (isConfirmed) void store.resetOrder();
    },
  };
};
