import type { PageDetails } from '../domain/page-details.ts';

export interface PageChanges {
  readonly manualNumber?: number | null;
  readonly isExcluded?: boolean;
  readonly rotation?: number;
}

export interface PageStore {
  readPage(pageId: string, signal: AbortSignal): Promise<PageDetails>;
  readPageHtml(pageId: string, signal: AbortSignal): Promise<string>;
  updatePage(pageId: string, changes: PageChanges): Promise<void>;
  readPageAgain(pageId: string): Promise<void>;
  deletePage(pageId: string): Promise<void>;
}
