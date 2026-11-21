import { showsSearch } from './document-search.ts';
import type { DocumentSummary } from './document-summary.ts';

export const LIBRARY_VIEWS = ['cards', 'list'] as const;

export type LibraryView = (typeof LIBRARY_VIEWS)[number];

export const DEFAULT_LIBRARY_VIEW: LibraryView = 'cards';

export const isLibraryView = (text: string): text is LibraryView => {
  return LIBRARY_VIEWS.some((view) => view === text);
};

// The switch sits in the toolbar, which a library too small for the search does without.
export const libraryViewInEffect = (documents: readonly DocumentSummary[], chosenView: LibraryView): LibraryView => {
  return showsSearch(documents) ? chosenView : DEFAULT_LIBRARY_VIEW;
};
