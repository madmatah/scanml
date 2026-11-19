import {
  type FC,
  memo,
  useCallback,
  useEffect,
  useId,
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
  organizerToolbar,
} from '../../../application/organizer-store.ts';
import type { DocumentWithPages, PageSummary } from '../../../domain/document-details.ts';
import {
  inOrder,
  type PageId,
  type ReadingOrder,
  readingOrderGroups,
  sameOrder,
} from '../../../domain/reading-order.ts';
import { pageShortLabel } from '../../i18next/page-labels.ts';
import { ConfirmDialog } from '../dialogs/confirm-dialog.tsx';
import { PlacementChip } from '../document/placement-chip.tsx';
import { Icon } from '../shell/icon.tsx';
import type { Toasts } from '../shell/toasts.ts';
import { versionedUrl } from '../shell/versioned-url.ts';
import type { GestureOutcome } from './drag-gesture.ts';
import { MoveDialog, type MoveTarget } from './move-dialog.tsx';
import {
  conflictText,
  type MoveChoice,
  moveChoices,
  moveText,
  organizerNotice,
  outsideText,
  pageName,
  placedHeadingText,
  placedHintText,
  selectionStatusText,
  spanLongText,
  spanShortText,
  unplacedHeadingText,
} from './organizer-text.ts';
import { createPageDrag } from './page-drag.ts';

export interface PageOrganizerProps {
  readonly document: DocumentWithPages;
  readonly save: (order: ReadingOrder) => Promise<DocumentWithPages>;
  readonly reset: () => Promise<DocumentWithPages>;
  readonly reload: () => void;
  readonly toasts: Toasts;
  readonly onDone: () => void;
}

type OpenDialog =
  | { readonly kind: 'move'; readonly moving: readonly PageId[]; readonly choices: readonly MoveChoice[] }
  | { readonly kind: 'reset' }
  | null;

type CardNodes = Map<PageId, HTMLLIElement>;

const ESCAPE = 'Escape';
const APP_HEADER_ID = 'app-header';
// The live region is emptied first, so that the same message twice is read twice.
const ANNOUNCE_DELAY_MILLISECONDS = 60;
const BEFORE = -1;
const AFTER = 1;

// aria-disabled rather than disabled, so that a focused button keeps the focus.
const unavailable = (isUnavailable: boolean): 'true' | undefined => {
  return isUnavailable ? 'true' : undefined;
};

const isUnavailable = (button: Element): boolean => {
  return button.getAttribute('aria-disabled') === 'true';
};

const closestElement = (target: EventTarget | null, selector: string): Element | null => {
  return target instanceof Element ? target.closest(selector) : null;
};

// The click on the lists selects, with the keys it holds; the checkbox only shows the selection.
const showsSelectionOnly = (): void => {};

const highlight = (cards: CardNodes, moved: readonly PageId[]): void => {
  for (const pageId of moved) {
    const node = cards.get(pageId);
    if (node === undefined) continue;
    node.classList.remove('is-moved');
    void node.offsetWidth;
    node.classList.add('is-moved');
  }
};

export const PageOrganizer: FC<PageOrganizerProps> = ({ document, save, reset, reload, toasts, onDone }) => {
  const { t } = useTranslation();
  const titleId = useId();
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
  const [openDialog, setOpenDialog] = useState<OpenDialog>(null);
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
  const toolbarState = organizerToolbar(snapshot);
  const groups = readingOrderGroups(order, pages);
  const outsideCount = snapshot.document.pages.length - order.length;

  const openMoveDialog = (): void => {
    const moving = inOrder(order, selection.selected);
    if (moving.length === 0 || moving.length === order.length || isResetting) return;
    setOpenDialog({ kind: 'move', moving, choices: moveChoices(t, pages, order, moving) });
  };

  const moveClosed = (moving: readonly PageId[], target: MoveTarget | null): void => {
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
  };

  const resetClosed = (isConfirmed: boolean): void => {
    setOpenDialog(null);
    // resetOrder tells its outcome through the store's report, so its promise never rejects.
    if (isConfirmed) void store.resetOrder();
  };

  const renderCards = (pageIds: readonly PageId[], firstIndex: number) => {
    return pageIds.map((pageId, offset) => {
      const page = pages.get(pageId);
      if (page === undefined) return null;
      return (
        <MemoizedOrganizerCard
          key={pageId}
          page={page}
          index={firstIndex + offset}
          total={order.length}
          isSelected={selection.selected.has(pageId)}
          isMoved={movedPageIds.has(pageId)}
          isResetting={isResetting}
          showsUnplaced={groups.hasPlacedPages}
          cards={cards.current}
        />
      );
    });
  };

  return (
    <section
      ref={organizer}
      className={isResetting ? 'organizer is-busy' : 'organizer'}
      aria-labelledby={titleId}
      aria-busy={unavailable(isResetting)}
    >
      <div ref={toolbar} className="organizer-toolbar">
        <div className="organizer-heading">
          <h3 ref={title} id={titleId} className="organizer-title" tabIndex={-1}>
            {t('Organize pages')}
          </h3>
          <p className="organizer-status">{selectionStatusText(t, toolbarState.selectedCount, order.length)}</p>
          <p className="organizer-saving" hidden={!toolbarState.showsSaving}>
            <span className="spinner" aria-hidden="true" />
            {t('Saving…')}
          </p>
        </div>
        <div className="organizer-actions">
          <button
            type="button"
            className="btn btn-small btn-compact"
            aria-disabled={unavailable(!toolbarState.canClearSelection)}
            onClick={() => {
              if (toolbarState.canClearSelection) store.clearSelection();
            }}
          >
            <Icon name="x" />
            <span className="btn-label">{t('Deselect all')}</span>
          </button>
          <button
            type="button"
            className="btn btn-small"
            hidden={!toolbarState.showsSpan}
            onClick={() => {
              store.selectSpan();
              // This button goes now that the range is whole: moving it is the next step.
              moveButton.current?.focus();
            }}
          >
            <span className="label-long">{spanLongText(t, toolbarState.spanCount)}</span>
            <span className="label-short">{spanShortText(t, toolbarState.spanCount)}</span>
          </button>
          <button
            ref={moveButton}
            type="button"
            className="btn btn-small"
            aria-disabled={unavailable(!toolbarState.canMoveSelection)}
            onClick={() => {
              if (toolbarState.canMoveSelection) openMoveDialog();
            }}
          >
            <Icon name="move" />
            <span className="label-long">{t('Move selection…')}</span>
            <span className="label-short">{t('Move…')}</span>
          </button>
          <button type="button" className="btn btn-primary btn-small" onClick={onDone}>
            <Icon name="check" />
            {t('Done')}
          </button>
        </div>
      </div>
      <div className="organizer-intro">
        <div className="organizer-help">
          <p className="hint hint-fine-pointer">
            {t(
              'Drag a page to move it: if it is selected, the whole selection follows it. Click: select, Shift+click: range, Ctrl+click: add or remove. Esc cancels a move.',
            )}
          </p>
          <p className="hint hint-coarse-pointer">
            {t(
              'Tap a page to select it, check others, then drag it by the handle (top right of the thumbnail) or after a long press.',
            )}
          </p>
          <p className="hint" hidden={outsideCount === 0}>
            {outsideText(t, outsideCount)}
          </p>
        </div>
        <button
          ref={resetButton}
          type="button"
          className="btn btn-small"
          hidden={!toolbarState.showsReset}
          aria-disabled={unavailable(!toolbarState.canReset)}
          onClick={() => {
            if (toolbarState.canReset) setOpenDialog({ kind: 'reset' });
          }}
        >
          <Icon name="undo" />
          {t('Restore automatic order')}
        </button>
      </div>
      <div ref={lists} className="organizer-lists">
        <section className="organizer-group">
          <div className="page-group-header">
            <h4 className="page-group-title">{placedHeadingText(t, groups.placed.length)}</h4>
            <p className="page-group-hint">{placedHintText(t, order.length, groups.hasPlacedPages)}</p>
          </div>
          {/* biome-ignore lint/a11y/noRedundantRoles: Safari drops the role of a list drawn without its markers. */}
          <ol className="page-grid organizer-grid" role="list">
            {renderCards(groups.placed, 0)}
          </ol>
        </section>
        <section className="organizer-group" hidden={groups.unplaced.length === 0}>
          <div className="page-group-header">
            <h4 className="page-group-title">{unplacedHeadingText(t, groups.unplaced.length)}</h4>
            <p className="page-group-hint">
              {t('Nothing tells where they go: they are at the end of the document. Drag them to their place.')}
            </p>
          </div>
          {/* biome-ignore lint/a11y/noRedundantRoles: Safari drops the role of a list drawn without its markers. */}
          <ol className="page-grid organizer-grid" role="list">
            {renderCards(groups.unplaced, groups.placed.length)}
          </ol>
        </section>
        <span ref={indicator} className="drop-indicator" hidden aria-hidden="true" />
      </div>
      <p ref={announcer} className="visually-hidden" aria-live="polite" />
      {openDialog?.kind === 'move' && (
        <MoveDialog
          count={openDialog.moving.length}
          choices={openDialog.choices}
          onClosed={(target) => moveClosed(openDialog.moving, target)}
        />
      )}
      {openDialog?.kind === 'reset' && (
        <ConfirmDialog
          title={t('Restore automatic order?')}
          message={t(
            'The pages will go back to the place given by their number or by their photo series. Moves made by hand will be forgotten.',
          )}
          confirmLabel={t('Restore automatic order')}
          onClosed={resetClosed}
        />
      )}
    </section>
  );
};

interface OrganizerCardProps {
  readonly page: PageSummary;
  readonly index: number;
  readonly total: number;
  readonly isSelected: boolean;
  readonly isMoved: boolean;
  readonly isResetting: boolean;
  readonly showsUnplaced: boolean;
  readonly cards: CardNodes;
}

const OrganizerCard: FC<OrganizerCardProps> = ({
  page,
  index,
  total,
  isSelected,
  isMoved,
  isResetting,
  showsUnplaced,
  cards,
}) => {
  const { t } = useTranslation();
  const name = pageName(t, page, index);
  const pageId = page.id;
  const register = useCallback(
    (node: HTMLLIElement | null) => {
      if (node === null) return;
      cards.set(pageId, node);
      return () => {
        if (cards.get(pageId) === node) cards.delete(pageId);
      };
    },
    [cards, pageId],
  );
  const classes = ['organizer-card', isSelected && 'is-selected', isMoved && 'is-moved'];
  return (
    <li ref={register} className={classes.filter(Boolean).join(' ')} data-id={pageId}>
      <div className="organizer-card-frame">
        <span className="page-thumb">
          {/* The api draws the thumbnail of a rotated page again at the same address. */}
          <img
            src={versionedUrl(page.thumbnailUrl, String(page.rotation))}
            alt=""
            loading="lazy"
            decoding="async"
            draggable={false}
          />
          <span className="organizer-index" aria-hidden="true">
            {String(index + 1)}
          </span>
          <span className="drag-handle" title={t('Drag to move')} aria-hidden="true">
            <Icon name="grip" />
          </span>
          <label className="organizer-check">
            <input
              type="checkbox"
              name="selected-pages"
              value={pageId}
              checked={isSelected}
              onChange={showsSelectionOnly}
              aria-label={t('Select {{page}}', { page: name })}
            />
          </label>
        </span>
        <span className="page-card-body">
          <span className="page-card-label">{pageShortLabel(t, { page_label: page.pageLabel })}</span>
          <PlacementChip page={page} showsUnplaced={showsUnplaced} />
        </span>
        <span className="organizer-steps">
          <button
            type="button"
            className="btn btn-icon btn-small"
            title={t('Place before the previous one')}
            data-step="-1"
            aria-label={t('Place {{page}} before the previous one', { page: name })}
            aria-disabled={unavailable(index === 0 || isResetting)}
          >
            <Icon name="chevron-left" />
          </button>
          <button
            type="button"
            className="btn btn-icon btn-small"
            title={t('Place after the next one')}
            data-step="1"
            aria-label={t('Place {{page}} after the next one', { page: name })}
            aria-disabled={unavailable(index === total - 1 || isResetting)}
          >
            <Icon name="chevron-right" />
          </button>
        </span>
      </div>
    </li>
  );
};

const MemoizedOrganizerCard = memo(OrganizerCard);
