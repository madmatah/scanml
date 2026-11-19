import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { samplePage } from '../domain/document-details.test-support.ts';
import type { DocumentWithPages, PageSummary } from '../domain/document-details.ts';
import { sampleDocument } from '../domain/document-summary.test-support.ts';
import type { ReadingOrder } from '../domain/reading-order.ts';
import { ApiError } from './api-errors.ts';
import {
  createOrganizerStore,
  type OrganizerEvent,
  type OrganizerMove,
  type OrganizerPlacement,
  type OrganizerSnapshot,
  type OrganizerStore,
  type OrganizerToolbar,
  organizerToolbar,
} from './organizer-store.ts';

interface PendingWrite {
  readonly order: ReadingOrder | null;
  readonly answer: (document: DocumentWithPages) => Promise<void>;
  readonly fail: (failure: unknown) => Promise<void>;
}

interface Arrangement {
  readonly store: OrganizerStore;
  readonly saves: PendingWrite[];
  readonly resets: PendingWrite[];
  readonly events: OrganizerEvent[];
  readonly reloads: string[];
}

const CONFLICT = 409;
const SERVER_ERROR = 500;
const PLAIN_CLICK = { isToggle: false, isRange: false };
const CTRL_CLICK = { isToggle: true, isRange: false };

const settle = async (): Promise<void> => {
  await new Promise((resolve) => setImmediate(resolve));
};

const documentWithOrder = (order: readonly string[], outside: readonly PageSummary[] = []): DocumentWithPages => {
  return {
    ...sampleDocument({ title: 'Example Book' }),
    slug: 'example-book',
    notes: '',
    unwarp: false,
    folder: '/data/USER/scanmylib/library/example-book',
    pages: [...order.map((pageId) => samplePage(pageId)), ...outside],
  };
};

const pendingWrites = (writes: PendingWrite[]): ((order?: ReadingOrder) => Promise<DocumentWithPages>) => {
  return (order) =>
    new Promise((resolve, reject) => {
      writes.push({
        order: order ?? null,
        answer: async (document) => {
          resolve(document);
          await settle();
        },
        fail: async (failure) => {
          reject(failure);
          await settle();
        },
      });
    });
};

const arrange = (document: DocumentWithPages): Arrangement => {
  const saves: PendingWrite[] = [];
  const resets: PendingWrite[] = [];
  const events: OrganizerEvent[] = [];
  const reloads: string[] = [];
  const store = createOrganizerStore(document, {
    save: pendingWrites(saves),
    reset: pendingWrites(resets),
    reload: () => reloads.push('reload'),
    report: (event) => events.push(event),
  });
  return { store, saves, resets, events, reloads };
};

const selectedOf = (snapshot: OrganizerSnapshot): string[] => {
  return [...snapshot.selection.selected].sort();
};

describe('The organizer store', () => {
  describe('The change() method', () => {
    describe('When a page is moved', () => {
      let arrangement: Arrangement;
      let shown: OrganizerSnapshot;
      beforeEach(() => {
        arrangement = arrange(documentWithOrder(['a', 'b', 'c']));
        arrangement.store.change(['b', 'a', 'c']);
        shown = arrangement.store.getSnapshot();
      });

      it('should show the new order at once, while it is being saved', () => {
        assert.deepEqual({ order: shown.order, isSaving: shown.isSaving }, { order: ['b', 'a', 'c'], isSaving: true });
      });

      it('should send it', () => {
        assert.deepEqual(
          arrangement.saves.map((save) => save.order),
          [['b', 'a', 'c']],
        );
      });

      describe('When the api answers the document in its new order', () => {
        beforeEach(async () => {
          await arrangement.saves[0]?.answer(documentWithOrder(['b', 'a', 'c']));
          shown = arrangement.store.getSnapshot();
        });

        it('should show that document, saved', () => {
          assert.deepEqual(
            { order: shown.order, isSaving: shown.isSaving, isDirty: shown.isDirty },
            { order: ['b', 'a', 'c'], isSaving: false, isDirty: false },
          );
        });
      });
    });

    describe('When pages are moved while an order is being sent', () => {
      let arrangement: Arrangement;
      let saveCountMeanwhile: number;
      beforeEach(async () => {
        arrangement = arrange(documentWithOrder(['a', 'b', 'c']));
        arrangement.store.change(['b', 'a', 'c']);
        arrangement.store.change(['b', 'c', 'a']);
        arrangement.store.change(['c', 'b', 'a']);
        saveCountMeanwhile = arrangement.saves.length;
        await arrangement.saves[0]?.answer(documentWithOrder(['b', 'a', 'c']));
      });

      it('should send one request at a time', () => {
        assert.equal(saveCountMeanwhile, 1);
      });

      it('should send the last order once the request has its answer, together', () => {
        assert.deepEqual(
          arrangement.saves.map((save) => save.order),
          [
            ['b', 'a', 'c'],
            ['c', 'b', 'a'],
          ],
        );
      });

      it('should keep showing the last order, not the answer to the first', () => {
        assert.deepEqual(arrangement.store.getSnapshot().order, ['c', 'b', 'a']);
      });
    });

    describe('When pages joined or left the reading order meanwhile', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(documentWithOrder(['a', 'b', 'c']));
        arrangement.store.change(['b', 'a', 'c']);
        await arrangement.saves[0]?.fail(new ApiError(CONFLICT, 'page set changed'));
      });

      it('should tell the conflict, and load the document again', () => {
        assert.deepEqual(
          { events: arrangement.events, reloads: arrangement.reloads },
          {
            events: [{ kind: 'conflict' }],
            reloads: ['reload'],
          },
        );
      });

      it('should show the last order the api gave', () => {
        assert.deepEqual(arrangement.store.getSnapshot().order, ['a', 'b', 'c']);
      });
    });

    describe('When the api fails to save the order', () => {
      const failure = new ApiError(SERVER_ERROR, 'database locked');
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(documentWithOrder(['a', 'b', 'c']));
        arrangement.store.change(['b', 'a', 'c']);
        await arrangement.saves[0]?.fail(failure);
      });

      it('should tell the failure, without loading the document again', () => {
        assert.deepEqual(
          { events: arrangement.events, reloads: arrangement.reloads },
          {
            events: [{ kind: 'save-failed', failure }],
            reloads: [],
          },
        );
      });

      it('should show the last order the api gave', () => {
        assert.deepEqual(arrangement.store.getSnapshot().order, ['a', 'b', 'c']);
      });
    });
  });

  describe('The moveOne() method', () => {
    describe('When a page is moved after the next one', () => {
      let arrangement: Arrangement;
      let move: OrganizerMove;
      beforeEach(() => {
        arrangement = arrange(documentWithOrder(['a', 'b', 'c']));
        move = arrangement.store.moveOne('a', 1);
      });

      it('should show the new order at once', () => {
        assert.deepEqual(arrangement.store.getSnapshot().order, ['b', 'a', 'c']);
      });

      it('should send it', () => {
        assert.deepEqual(
          arrangement.saves.map((save) => save.order),
          [['b', 'a', 'c']],
        );
      });

      it('should tell that the page moved, so that its card can be highlighted', () => {
        assert.deepEqual(move, { kind: 'moved', moved: ['a'] });
      });
    });

    describe('When the first page is moved before the previous one', () => {
      let arrangement: Arrangement;
      let move: OrganizerMove;
      beforeEach(() => {
        arrangement = arrange(documentWithOrder(['a', 'b', 'c']));
        move = arrangement.store.moveOne('a', -1);
      });

      it('should keep the order, without sending it', () => {
        assert.deepEqual(
          { order: arrangement.store.getSnapshot().order, saveCount: arrangement.saves.length },
          { order: ['a', 'b', 'c'], saveCount: 0 },
        );
      });

      it('should tell that nothing moved', () => {
        assert.deepEqual(move, { kind: 'unchanged' });
      });
    });
  });

  describe('The place() method', () => {
    describe('When selected pages are placed after another', () => {
      let arrangement: Arrangement;
      let placement: OrganizerPlacement;
      beforeEach(() => {
        arrangement = arrange(documentWithOrder(['a', 'b', 'c', 'd']));
        placement = arrangement.store.place(['a', 'b'], 'd', 'after');
      });

      it('should show the new order at once', () => {
        assert.deepEqual(arrangement.store.getSnapshot().order, ['c', 'd', 'a', 'b']);
      });

      it('should send it', () => {
        assert.deepEqual(
          arrangement.saves.map((save) => save.order),
          [['c', 'd', 'a', 'b']],
        );
      });

      it('should tell the pages moved, so that their cards can be highlighted', () => {
        assert.deepEqual(placement, { kind: 'moved', moved: ['a', 'b'] });
      });
    });

    describe('When the pages are placed where they already are', () => {
      let arrangement: Arrangement;
      let placement: OrganizerPlacement;
      beforeEach(() => {
        arrangement = arrange(documentWithOrder(['a', 'b', 'c']));
        placement = arrangement.store.place(['a', 'b'], 'c', 'before');
      });

      it('should keep the order, without sending it', () => {
        assert.deepEqual(
          { order: arrangement.store.getSnapshot().order, saveCount: arrangement.saves.length },
          { order: ['a', 'b', 'c'], saveCount: 0 },
        );
      });

      it('should tell that nothing moved', () => {
        assert.deepEqual(placement, { kind: 'unchanged' });
      });
    });

    describe('When the target page left the reading order meanwhile', () => {
      let arrangement: Arrangement;
      let placement: OrganizerPlacement;
      beforeEach(() => {
        arrangement = arrange(documentWithOrder(['a', 'b'], [samplePage('x', { isInDocument: false })]));
        placement = arrangement.store.place(['a'], 'x', 'after');
      });

      it('should keep the order, without sending it', () => {
        assert.deepEqual(
          { order: arrangement.store.getSnapshot().order, saveCount: arrangement.saves.length },
          { order: ['a', 'b'], saveCount: 0 },
        );
      });

      it('should tell the conflict', () => {
        assert.deepEqual(placement, { kind: 'conflict' });
      });
    });

    describe('When a page to place left the reading order meanwhile', () => {
      let arrangement: Arrangement;
      let placement: OrganizerPlacement;
      beforeEach(() => {
        arrangement = arrange(documentWithOrder(['a', 'b', 'c'], [samplePage('x', { isInDocument: false })]));
        placement = arrangement.store.place(['a', 'x'], 'c', 'after');
      });

      it('should keep the order, without sending it', () => {
        assert.deepEqual(
          { order: arrangement.store.getSnapshot().order, saveCount: arrangement.saves.length },
          { order: ['a', 'b', 'c'], saveCount: 0 },
        );
      });

      it('should tell the conflict', () => {
        assert.deepEqual(placement, { kind: 'conflict' });
      });
    });
  });

  describe('The update() method', () => {
    describe('When a newer document comes while an order is being sent', () => {
      let arrangement: Arrangement;
      let orderMeanwhile: ReadingOrder;
      beforeEach(async () => {
        arrangement = arrange(documentWithOrder(['a', 'b', 'c']));
        arrangement.store.change(['b', 'a', 'c']);
        arrangement.store.update(documentWithOrder(['a', 'b', 'c', 'd']));
        orderMeanwhile = arrangement.store.getSnapshot().order;
        await arrangement.saves[0]?.answer(documentWithOrder(['b', 'a', 'c', 'd']));
      });

      it('should keep the order on screen meanwhile, so that the move does not jump back', () => {
        assert.deepEqual(orderMeanwhile, ['b', 'a', 'c']);
      });

      it('should show the document of the answer once the order is saved', () => {
        assert.deepEqual(arrangement.store.getSnapshot().order, ['b', 'a', 'c', 'd']);
      });
    });

    describe('When a newer document comes during a gesture', () => {
      let arrangement: Arrangement;
      let orderMeanwhile: ReadingOrder;
      beforeEach(() => {
        arrangement = arrange(documentWithOrder(['a', 'b', 'c']));
        arrangement.store.beginGesture();
        arrangement.store.update(documentWithOrder(['a', 'b', 'c', 'd']));
        orderMeanwhile = arrangement.store.getSnapshot().order;
        arrangement.store.endGesture();
      });

      it('should keep the cards where they are until the gesture ends, so that the drop lands where it was aimed', () => {
        assert.deepEqual(orderMeanwhile, ['a', 'b', 'c']);
      });

      it('should show it once the gesture ends', () => {
        assert.deepEqual(arrangement.store.getSnapshot().order, ['a', 'b', 'c', 'd']);
      });
    });

    describe('When selected pages left the reading order', () => {
      let arrangement: Arrangement;
      let shown: OrganizerSnapshot;
      beforeEach(() => {
        arrangement = arrange(documentWithOrder(['a', 'b', 'c']));
        arrangement.store.select('a', PLAIN_CLICK);
        arrangement.store.select('c', CTRL_CLICK);
        arrangement.store.update(documentWithOrder(['a', 'b'], [samplePage('c', { isInDocument: false })]));
        shown = arrangement.store.getSnapshot();
      });

      it('should drop them from the selection and from the anchor', () => {
        assert.deepEqual(
          { selected: selectedOf(shown), anchor: shown.selection.anchor },
          {
            selected: ['a'],
            anchor: null,
          },
        );
      });
    });
  });

  describe('The resetOrder() method', () => {
    describe('When the automatic order is restored while an order is being sent', () => {
      let arrangement: Arrangement;
      let resetCountWhileSaving: number;
      let isResettingMeanwhile: boolean;
      let restoring: Promise<void>;
      beforeEach(async () => {
        arrangement = arrange(documentWithOrder(['a', 'b', 'c']));
        arrangement.store.change(['c', 'a', 'b']);
        restoring = arrangement.store.resetOrder();
        await settle();
        resetCountWhileSaving = arrangement.resets.length;
        await arrangement.saves[0]?.answer(documentWithOrder(['c', 'a', 'b']));
        isResettingMeanwhile = arrangement.store.getSnapshot().isResetting;
        await arrangement.resets[0]?.answer(documentWithOrder(['a', 'b', 'c']));
        await restoring;
      });

      it('should wait until the order is saved', () => {
        assert.equal(resetCountWhileSaving, 0);
      });

      it('should show that the order is being restored', () => {
        assert.equal(isResettingMeanwhile, true);
      });

      it('should tell that it is restored', () => {
        assert.deepEqual(arrangement.events, [{ kind: 'reset-done' }]);
      });

      it('should show the document in its automatic order', () => {
        assert.deepEqual(arrangement.store.getSnapshot().order, ['a', 'b', 'c']);
      });
    });

    describe('When the api fails to restore the automatic order', () => {
      const failure = new ApiError(SERVER_ERROR, 'database locked');
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(documentWithOrder(['c', 'a', 'b']));
        const restoring = arrangement.store.resetOrder();
        await settle();
        await arrangement.resets[0]?.fail(failure);
        await restoring;
      });

      it('should tell the failure', () => {
        assert.deepEqual(arrangement.events, [{ kind: 'reset-failed', failure }]);
      });

      it('should keep the order the api gave, no longer restoring', () => {
        const shown = arrangement.store.getSnapshot();
        assert.deepEqual(
          { order: shown.order, isResetting: shown.isResetting },
          {
            order: ['c', 'a', 'b'],
            isResetting: false,
          },
        );
      });
    });
  });

  describe('The selectSpan() method', () => {
    describe('When scattered pages are selected', () => {
      let shown: OrganizerSnapshot;
      beforeEach(() => {
        const { store } = arrange(documentWithOrder(['a', 'b', 'c', 'd']));
        store.select('a', PLAIN_CLICK);
        store.select('c', CTRL_CLICK);
        store.selectSpan();
        shown = store.getSnapshot();
      });

      it('should select every page between them', () => {
        assert.deepEqual(selectedOf(shown), ['a', 'b', 'c']);
      });
    });
  });

  describe('The clearSelection() method', () => {
    describe('When pages are selected', () => {
      let shown: OrganizerSnapshot;
      beforeEach(() => {
        const { store } = arrange(documentWithOrder(['a', 'b', 'c']));
        store.select('a', PLAIN_CLICK);
        store.clearSelection();
        shown = store.getSnapshot();
      });

      it('should empty the selection and its anchor', () => {
        assert.deepEqual(
          { selected: selectedOf(shown), anchor: shown.selection.anchor },
          { selected: [], anchor: null },
        );
      });
    });
  });

  describe('The organizerToolbar() function', () => {
    describe('When scattered pages are selected and an order is being sent', () => {
      let toolbar: OrganizerToolbar;
      beforeEach(() => {
        const { store } = arrange(documentWithOrder(['a', 'b', 'c', 'd']));
        store.select('a', PLAIN_CLICK);
        store.select('c', CTRL_CLICK);
        store.change(['b', 'a', 'd', 'c']);
        toolbar = organizerToolbar(store.getSnapshot());
      });

      it('should offer to move or to clear the selection, and to select the range between', () => {
        assert.deepEqual(toolbar, {
          selectedCount: 2,
          canClearSelection: true,
          canMoveSelection: true,
          spanCount: 3,
          showsSpan: true,
          showsReset: true,
          canReset: false,
          showsSaving: true,
        });
      });
    });

    describe('When every page is selected', () => {
      let toolbar: OrganizerToolbar;
      beforeEach(() => {
        const { store } = arrange(documentWithOrder(['a', 'b']));
        store.select('a', PLAIN_CLICK);
        store.select('b', CTRL_CLICK);
        toolbar = organizerToolbar(store.getSnapshot());
      });

      it('should not offer to move them, since they have nowhere to go', () => {
        assert.equal(toolbar.canMoveSelection, false);
      });
    });

    describe('When a page outside the reading order keeps a place chosen by hand', () => {
      let toolbar: OrganizerToolbar;
      beforeEach(() => {
        const excluded = samplePage('x', { isInDocument: false, isExcluded: true, position: 1.5 });
        toolbar = organizerToolbar(arrange(documentWithOrder(['a', 'b'], [excluded])).store.getSnapshot());
      });

      it('should offer to restore the automatic order', () => {
        assert.deepEqual(
          { showsReset: toolbar.showsReset, canReset: toolbar.canReset },
          {
            showsReset: true,
            canReset: true,
          },
        );
      });
    });

    describe('When every page has its automatic place', () => {
      let toolbar: OrganizerToolbar;
      beforeEach(() => {
        toolbar = organizerToolbar(arrange(documentWithOrder(['a', 'b'])).store.getSnapshot());
      });

      it('should not offer to restore the automatic order, nor show a save', () => {
        assert.deepEqual(
          { showsReset: toolbar.showsReset, showsSaving: toolbar.showsSaving },
          {
            showsReset: false,
            showsSaving: false,
          },
        );
      });
    });
  });
});
