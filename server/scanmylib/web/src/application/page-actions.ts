import type { PageChanges, PageStore } from './page-store.ts';

export type PageAction =
  | { readonly kind: 'saveNumber'; readonly number: number }
  | { readonly kind: 'clearNumber' }
  | { readonly kind: 'rotate'; readonly rotation: number }
  | { readonly kind: 'setExclusion'; readonly isExcluded: boolean }
  | { readonly kind: 'readAgain' };

export type PageActionOutcome =
  | { readonly kind: 'succeeded'; readonly action: PageAction }
  | { readonly kind: 'failed'; readonly action: PageAction; readonly failure: unknown };

export type PageDeletion = { readonly kind: 'deleted' } | { readonly kind: 'failed'; readonly failure: unknown };

export interface PageActionsOptions {
  readonly pageId: string;
  readonly pages: Pick<PageStore, 'updatePage' | 'readPageAgain' | 'deletePage'>;
  readonly reload: () => Promise<void>;
  readonly onBusyChange: (isBusy: boolean) => void;
}

export interface PageActions {
  run(action: PageAction, onOutcome: (outcome: PageActionOutcome) => void): Promise<void>;
  deletePage(onDeletion: (deletion: PageDeletion) => void): Promise<void>;
}

const changesOf = (action: Exclude<PageAction, { readonly kind: 'readAgain' }>): PageChanges => {
  switch (action.kind) {
    case 'saveNumber':
      return { manualNumber: action.number };
    case 'clearNumber':
      return { manualNumber: null };
    case 'rotate':
      return { rotation: action.rotation };
    case 'setExclusion':
      return { isExcluded: action.isExcluded };
  }
};

export const createPageActions = ({ pageId, pages, reload, onBusyChange }: PageActionsOptions): PageActions => {
  // Set at once, so that a second click that comes before the first action's render is dropped.
  let isActing = false;

  const setActing = (isNowActing: boolean): void => {
    isActing = isNowActing;
    onBusyChange(isNowActing);
  };

  const request = (action: PageAction): Promise<void> => {
    return action.kind === 'readAgain' ? pages.readPageAgain(pageId) : pages.updatePage(pageId, changesOf(action));
  };

  const run = async (action: PageAction, onOutcome: (outcome: PageActionOutcome) => void): Promise<void> => {
    if (isActing) return;
    setActing(true);
    try {
      await request(action);
      onOutcome({ kind: 'succeeded', action });
    } catch (failure) {
      onOutcome({ kind: 'failed', action, failure });
    } finally {
      setActing(false);
    }
    await reload();
  };

  // The screen is left once its page is deleted, so the actions stay unavailable until then.
  const deletePage = async (onDeletion: (deletion: PageDeletion) => void): Promise<void> => {
    setActing(true);
    try {
      await pages.deletePage(pageId);
    } catch (failure) {
      onDeletion({ kind: 'failed', failure });
      setActing(false);
      return;
    }
    onDeletion({ kind: 'deleted' });
  };

  return { run, deletePage };
};
