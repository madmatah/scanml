import './app.css';

import { createRoot } from 'react-dom/client';
import { I18nextProvider } from 'react-i18next';
import { createHashRouter } from 'react-router';
import { RouterProvider } from 'react-router/dom';

import { takeSignInToken, watchSignInLinks } from './adapters/browser/address-bar.ts';
import { createPageVisibility } from './adapters/browser/page-visibility.ts';
import { createRandomUuidSource } from './adapters/browser/random-uuid-source.ts';
import { createSignInRecord } from './adapters/browser/sign-in-record.ts';
import { createTimerScheduler } from './adapters/browser/timer-scheduler.ts';
import { createApiClient } from './adapters/http-api/api-client.ts';
import { CATALOGS } from './adapters/i18next/catalogs.ts';
import { createLocalization } from './adapters/i18next/localization.ts';
import { createRoutes } from './adapters/react/shell/routes.tsx';
import { createToasts } from './adapters/react/shell/toasts.ts';
import { createEngineStatus } from './application/engine-status.ts';
import { createSession } from './application/session.ts';

function findElement(selector: string): Element {
  const element = document.querySelector(selector);
  if (element === null) throw new Error(`The entry page holds no ${selector}`);
  return element;
}

// Before anything else, so that the secret of a sign-in link never lingers in the address bar or the history; and the
// links opened later are watched before the router listens, so that it never reads one.
const linkToken = takeSignInToken(window);
const apiClient = createApiClient(
  (path, init) => fetch(path, init),
  () => session.expire(),
);
const scheduler = createTimerScheduler(window);
const session = createSession(
  apiClient,
  createSignInRecord(() => window.localStorage),
);
const engineStatus = createEngineStatus(apiClient, createPageVisibility(document), scheduler);
// The api tells its status only to a signed-in browser.
session.subscribe(() => {
  if (session.getSnapshot().phase === 'signed-in') engineStatus.start();
  else engineStatus.stop();
});
watchSignInLinks(window, (token) => {
  void session.signInWithLink(token);
});
const started = session.start(linkToken);
const toasts = createToasts(scheduler);

const localization = await createLocalization(CATALOGS);
const { t } = localization.i18next;
document.documentElement.lang = localization.language;
findElement('meta[name="description"]').setAttribute(
  'content',
  t('ScanMyLib: scan your books and documents with your phone; your PC reads their text.'),
);

createRoot(findElement('#app')).render(
  <I18nextProvider i18n={localization.i18next}>
    <RouterProvider
      router={createHashRouter(
        createRoutes({
          session,
          toasts,
          engineStatus,
          formatting: localization.formatting,
          dates: localization.dates,
          catalog: apiClient,
          uuids: createRandomUuidSource(window.crypto),
        }),
      )}
    />
  </I18nextProvider>,
);
await started;
