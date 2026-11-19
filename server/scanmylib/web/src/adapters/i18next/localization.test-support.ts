import type { Resource } from 'i18next';

import { createLocalization, type Localization } from './localization.ts';

// The language detector reads the browser's languages from the global navigator, and only while the instance starts.
export async function createLocalizationFor(
  browserLanguages: readonly string[] | undefined,
  catalogs: Resource,
): Promise<Localization> {
  const navigatorProperty = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  const browserNavigator = browserLanguages === undefined ? {} : { languages: browserLanguages };
  Object.defineProperty(globalThis, 'navigator', { value: browserNavigator, configurable: true });
  try {
    return await createLocalization(catalogs);
  } finally {
    Reflect.deleteProperty(globalThis, 'navigator');
    if (navigatorProperty !== undefined) Object.defineProperty(globalThis, 'navigator', navigatorProperty);
  }
}
