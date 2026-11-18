export const PATHS = { home: '/', login: '/login', pairing: '/pairing' } as const;

export type RouteName = 'home' | 'document' | 'reader' | 'page' | 'pairing' | 'login' | 'unknown';

export type Section = 'library' | 'pairing';

export type Access = 'signed-in' | 'signed-out' | 'just-signed-out';

export type Redirect =
  | { readonly to: 'login'; readonly returnTo: string | null; readonly replacesEntry: boolean }
  | { readonly to: 'return-path' };

export const BRAND_NAME = 'ScanMyLib';

// The api names its documents and pages by lowercase hyphenated UUIDs; an address may write them in capitals.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function documentPath(documentId: string): string {
  return `/documents/${documentId}`;
}

export function readerPath(documentId: string): string {
  return `/documents/${documentId}/read`;
}

export function pagePath(pageId: string): string {
  return `/pages/${pageId}`;
}

export function idOfAddress(segment: string | undefined): string | null {
  return segment !== undefined && UUID.test(segment) ? segment.toLowerCase() : null;
}

function isRouteName(name: string): name is RouteName {
  return (
    name === 'home' ||
    name === 'document' ||
    name === 'reader' ||
    name === 'page' ||
    name === 'pairing' ||
    name === 'login' ||
    name === 'unknown'
  );
}

export interface AddressIds {
  readonly documentId?: string | undefined;
  readonly pageId?: string | undefined;
}

export function routeNameOf(matchedId: string, { documentId, pageId }: AddressIds): RouteName {
  if (!isRouteName(matchedId)) return 'unknown';
  if ((matchedId === 'document' || matchedId === 'reader') && idOfAddress(documentId) === null) return 'unknown';
  if (matchedId === 'page' && idOfAddress(pageId) === null) return 'unknown';
  return matchedId;
}

export function redirectFor(access: Access, route: RouteName, path: string): Redirect | null {
  switch (access) {
    case 'signed-in':
      return route === 'login' || route === 'unknown' ? { to: 'return-path' } : null;
    case 'signed-out':
      if (route === 'login') return null;
      return { to: 'login', returnTo: route === 'unknown' ? null : path, replacesEntry: true };
    case 'just-signed-out':
      return route === 'login' ? null : { to: 'login', returnTo: null, replacesEntry: false };
  }
}

export function sectionOf(route: RouteName): Section | null {
  switch (route) {
    case 'home':
    case 'document':
    case 'reader':
    case 'page':
      return 'library';
    case 'pairing':
      return 'pairing';
    case 'login':
    case 'unknown':
      return null;
  }
}

export function documentTitle(screenTitle: string | null): string {
  return screenTitle === null ? BRAND_NAME : `${screenTitle} · ${BRAND_NAME}`;
}
