export const PATHS = { home: '/', login: '/login', pairing: '/pairing' } as const;

export type RouteName = 'home' | 'pairing' | 'login' | 'unknown';

export type Section = 'library' | 'pairing';

export type Access = 'signed-in' | 'signed-out' | 'just-signed-out';

export type Redirect =
  | { readonly to: 'login'; readonly returnTo: string | null; readonly replacesEntry: boolean }
  | { readonly to: 'return-path' };

export const BRAND_NAME = 'ScanMyLib';

export function documentPath(documentId: string): string {
  return `/documents/${documentId}`;
}

export function isRouteName(name: string): name is RouteName {
  return name === 'home' || name === 'pairing' || name === 'login' || name === 'unknown';
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
