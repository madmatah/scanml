import type { LibraryView } from '../domain/library-view.ts';

export interface LibraryViewPreference {
  readSaved(): LibraryView | null;
  save(view: LibraryView): void;
}
