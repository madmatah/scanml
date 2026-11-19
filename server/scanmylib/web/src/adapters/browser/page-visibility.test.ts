import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { createPageVisibility, type VisibleDocument } from './page-visibility.ts';

interface StubDocument extends VisibleDocument {
  hidden: boolean;
  readonly listeners: Set<() => void>;
}

const createStubDocument = (hidden: boolean): StubDocument => {
  const listeners = new Set<() => void>();
  return {
    hidden,
    listeners,
    addEventListener: (_type, listener) => {
      listeners.add(listener);
    },
    removeEventListener: (_type, listener) => {
      listeners.delete(listener);
    },
  };
};

describe('The page visibility', () => {
  describe('The isVisible() method', () => {
    describe('When the page is hidden', () => {
      let isVisible: boolean;
      beforeEach(() => {
        isVisible = createPageVisibility(createStubDocument(true)).isVisible();
      });

      it('should say that it is not visible', () => {
        assert.equal(isVisible, false);
      });
    });

    describe('When the page is shown', () => {
      let isVisible: boolean;
      beforeEach(() => {
        isVisible = createPageVisibility(createStubDocument(false)).isVisible();
      });

      it('should say that it is visible', () => {
        assert.equal(isVisible, true);
      });
    });
  });

  describe('The watch() method', () => {
    describe('When the visibility of the page changes', () => {
      let changeCount: number;
      beforeEach(() => {
        const page = createStubDocument(false);
        changeCount = 0;
        createPageVisibility(page).watch(() => {
          changeCount += 1;
        });
        page.hidden = true;
        for (const listener of page.listeners) listener();
      });

      it('should tell the watcher', () => {
        assert.equal(changeCount, 1);
      });
    });

    describe('When the watcher has stopped watching', () => {
      let page: StubDocument;
      beforeEach(() => {
        page = createStubDocument(false);
        const stopWatching = createPageVisibility(page).watch(() => {});
        stopWatching();
      });

      it('should no longer listen to the page', () => {
        assert.equal(page.listeners.size, 0);
      });
    });
  });
});
