export const PATHS = { home: '/', login: '/login' } as const;

export type RouteName = 'home' | 'login' | 'unknown';

export type Redirect = { readonly to: 'login'; readonly returnTo: string | null } | { readonly to: 'return-path' };

export const BRAND_NAME = 'ScanMyLib';

export function isRouteName(name: string): name is RouteName {
  return name === 'home' || name === 'login' || name === 'unknown';
}

export function redirectFor(isSignedIn: boolean, route: RouteName, path: string): Redirect | null {
  if (!isSignedIn) return route === 'login' ? null : { to: 'login', returnTo: route === 'unknown' ? null : path };
  return route === 'home' ? null : { to: 'return-path' };
}

export function documentTitle(screenTitle: string | null): string {
  return screenTitle === null ? BRAND_NAME : `${screenTitle} · ${BRAND_NAME}`;
}
