import '../static/css/app.css';

import { createRoot } from 'react-dom/client';
import { I18nextProvider } from 'react-i18next';

import { CATALOGS } from './adapters/i18next/catalogs.ts';
import { createLocalization } from './adapters/i18next/localization.ts';
import { LoadingState } from './adapters/react/shell/loading-state.tsx';

function findElement(selector: string): Element {
  const element = document.querySelector(selector);
  if (element === null) throw new Error(`The entry page holds no ${selector}`);
  return element;
}

const localization = await createLocalization(CATALOGS);
const { t } = localization.i18next;
document.documentElement.lang = localization.language;
findElement('meta[name="description"]').setAttribute(
  'content',
  t('ScanMyLib: scan your books and documents with your phone; your PC reads their text.'),
);

createRoot(findElement('#app')).render(
  <I18nextProvider i18n={localization.i18next}>
    <main className="app-main" id="main" tabIndex={-1}>
      <LoadingState />
    </main>
  </I18nextProvider>,
);
