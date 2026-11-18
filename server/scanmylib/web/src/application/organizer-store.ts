import { type DocumentWithPages, hasPagesPositionedByHand, type PageSummary } from '../domain/document-details.ts';
import { type PageId, type ReadingOrder, spanOf } from '../domain/reading-order.ts';
import {
  keepShownPages,
  NO_SELECTION,
  type Selection,
  type SelectionKeys,
  selectPage,
  selectSpan,
} from '../domain/selection.ts';
import { ApiError } from './api-errors.ts';

export type OrganizerEvent =
  | { readonly kind: 'conflict' }
  | { readonly kind: 'save-failed'; readonly failure: unknown }
  | { readonly kind: 'reset-done' }
  | { readonly kind: 'reset-failed'; readonly failure: unknown };

export interface OrganizerPorts {
  readonly save: (order: ReadingOrder) => Promise<DocumentWithPages>;
  readonly reset: () => Promise<DocumentWithPages>;
  readonly reload: () => void;
  readonly report: (event: OrganizerEvent) => void;
}

export interface OrganizerSnapshot {
  readonly document: DocumentWithPages;
  readonly pages: ReadonlyMap<PageId, PageSummary>;
  readonly order: ReadingOrder;
  readonly selection: Selection;
  readonly isDirty: boolean;
  readonly isSaving: boolean;
  readonly isResetting: boolean;
}

export interface OrganizerToolbar {
  readonly selectedCount: number;
  readonly canClearSelection: boolean;
  readonly canMoveSelection: boolean;
  readonly spanCount: number;
  readonly showsSpan: boolean;
  readonly showsReset: boolean;
  readonly canReset: boolean;
  readonly showsSaving: boolean;
}

export interface OrganizerStore {
  subscribe(listener: () => void): () => void;
  getSnapshot(): OrganizerSnapshot;
  update(document: DocumentWithPages): void;
  beginGesture(): void;
  endGesture(): void;
  change(order: ReadingOrder): void;
  select(pageId: PageId, keys: SelectionKeys): void;
  clearSelection(): void;
  selectSpan(): void;
  hasGesture(): boolean;
  resetOrder(): Promise<void>;
}

const CONFLICT = 409;

function isConflict(failure: unknown): boolean {
  return failure instanceof ApiError && failure.status === CONFLICT;
}

function readingOrderOf(document: DocumentWithPages): PageId[] {
  return document.pages.filter((page) => page.isInDocument).map((page) => page.id);
}

export function organizerToolbar(snapshot: OrganizerSnapshot): OrganizerToolbar {
  const { order, selection, isDirty, isSaving, isResetting } = snapshot;
  const selectedCount = selection.selected.size;
  const spanCount = spanOf(order, selection.selected).length;
  return {
    selectedCount,
    canClearSelection: selectedCount > 0,
    canMoveSelection: selectedCount > 0 && selectedCount !== order.length && !isResetting,
    spanCount,
    showsSpan: spanCount > selectedCount,
    showsReset: hasPagesPositionedByHand(snapshot.document.pages) || isDirty || isSaving,
    canReset: !isSaving && !isDirty && !isResetting,
    showsSaving: isSaving || isDirty || isResetting,
  };
}

export function createOrganizerStore(document: DocumentWithPages, ports: OrganizerPorts): OrganizerStore {
  let latest = document;
  let pages: ReadonlyMap<PageId, PageSummary> = new Map(document.pages.map((page) => [page.id, page]));
  let order: ReadingOrder = readingOrderOf(document);
  let selection = NO_SELECTION;
  let isDirty = false;
  let isSaving = false;
  let isResetting = false;
  let isGestureActive = false;
  const savedWaiters: (() => void)[] = [];
  const listeners = new Set<() => void>();

  function snapshotNow(): OrganizerSnapshot {
    return { document: latest, pages, order, selection, isDirty, isSaving, isResetting };
  }

  let snapshot = snapshotNow();

  function notify(): void {
    snapshot = snapshotNow();
    for (const listener of listeners) listener();
  }

  function showLatest(): void {
    pages = new Map(latest.pages.map((page) => [page.id, page]));
    order = readingOrderOf(latest);
    selection = keepShownPages(selection, order);
    notify();
  }

  function showLatestWhenIdle(): void {
    if (!isGestureActive && !isSaving && !isDirty && !isResetting) showLatest();
  }

  async function flush(): Promise<void> {
    if (isSaving || isResetting || !isDirty) return;
    isSaving = true;
    isDirty = false;
    notify();
    let failure: { readonly cause: unknown } | null = null;
    try {
      latest = await ports.save(order.slice());
    } catch (cause) {
      failure = { cause };
    }
    isSaving = false;
    if (failure !== null) {
      // The moves made meanwhile were made on the refused order.
      isDirty = false;
      if (isConflict(failure.cause)) {
        ports.report({ kind: 'conflict' });
        ports.reload();
      } else {
        ports.report({ kind: 'save-failed', failure: failure.cause });
      }
    } else if (isDirty) {
      // flush tells its failures through report, so its promise never rejects.
      void flush();
      return;
    }
    showLatestWhenIdle();
    notify();
    for (const resolve of savedWaiters.splice(0)) resolve();
  }

  function whenSaved(): Promise<void> {
    return isSaving || isDirty ? new Promise((resolve) => savedWaiters.push(resolve)) : Promise.resolve();
  }

  function replaceSelection(next: Selection): void {
    selection = next;
    notify();
  }

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    getSnapshot: () => snapshot,
    update(next) {
      if (next === latest) return;
      latest = next;
      showLatestWhenIdle();
    },
    beginGesture() {
      isGestureActive = true;
    },
    hasGesture: () => isGestureActive,
    endGesture() {
      isGestureActive = false;
      showLatestWhenIdle();
    },
    change(next) {
      order = next;
      isDirty = true;
      notify();
      // flush tells its failures through report, so its promise never rejects.
      void flush();
    },
    select: (pageId, keys) => replaceSelection(selectPage(selection, order, pageId, keys)),
    clearSelection: () => replaceSelection(NO_SELECTION),
    selectSpan: () => replaceSelection(selectSpan(selection, order)),
    async resetOrder() {
      await whenSaved();
      isResetting = true;
      notify();
      try {
        latest = await ports.reset();
        ports.report({ kind: 'reset-done' });
      } catch (failure) {
        ports.report({ kind: 'reset-failed', failure });
      } finally {
        isResetting = false;
        showLatest();
      }
    },
  };
}
