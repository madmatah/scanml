import { useEffect } from 'react';

import { documentTitle } from './navigation.ts';

export const useDocumentTitle = (screenTitle: string | null): void => {
  useEffect(() => {
    document.title = documentTitle(screenTitle);
  }, [screenTitle]);
};
