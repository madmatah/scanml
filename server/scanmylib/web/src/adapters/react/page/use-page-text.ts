import { type RefObject, useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { localizeMarkers } from '../sanitized-html/page-markers.ts';
import { type FormulaTypesetter, useSanitizedHtml } from '../sanitized-html/use-sanitized-html.ts';
import { versionedUrl } from '../shell/versioned-url.ts';

export const usePageText = (
  sanitizedHtml: string,
  version: string,
  typesetFormulas: FormulaTypesetter,
): RefObject<HTMLDivElement | null> => {
  const { t } = useTranslation();
  // The api writes its markers in English; the illustrations get the version of the reading before any of them loads.
  const prepare = useCallback(
    (content: DocumentFragment) => {
      localizeMarkers(t, content);
      for (const illustration of content.querySelectorAll('img[src]')) {
        const address = illustration.getAttribute('src');
        if (address !== null) illustration.setAttribute('src', versionedUrl(address, version));
      }
    },
    [t, version],
  );
  return useSanitizedHtml(sanitizedHtml, prepare, typesetFormulas);
};
