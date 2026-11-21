import type { LibraryViewPreference } from '../../application/library-view-preference.ts';
import { isLibraryView } from '../../domain/library-view.ts';
import type { KeyValueStorage } from './key-value-storage.ts';

// A name outside the program: a new one would forget the view that every browser chose before.
const LIBRARY_VIEW_KEY = 'scanmylib.library-view';

// The storage is reached on each call, since the browser throws when its storage is disabled, even on reaching it.
export const createLibraryViewPreference = (openStorage: () => KeyValueStorage): LibraryViewPreference => {
  return {
    readSaved() {
      try {
        const saved = openStorage().getItem(LIBRARY_VIEW_KEY);
        return saved !== null && isLibraryView(saved) ? saved : null;
      } catch {
        return null;
      }
    },
    save(view) {
      try {
        openStorage().setItem(LIBRARY_VIEW_KEY, view);
      } catch {
        // A disabled storage remembers nothing, and the next visit shows the cards.
      }
    },
  };
};
