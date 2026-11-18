import { useEffect, useLayoutEffect, useRef, useSyncExternalStore } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useLocation, useMatches, useNavigate } from 'react-router';

import type { Session } from '../../../application/session.ts';
import { LoadingState } from './loading-state.tsx';
import { isRouteName, PATHS, type RouteName, redirectFor } from './navigation.ts';

function useRouteName(): RouteName {
  const id = useMatches().at(-1)?.id ?? 'unknown';
  return isRouteName(id) ? id : 'unknown';
}

export function Shell({ session }: { readonly session: Session }) {
  const { t } = useTranslation();
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot);
  const location = useLocation();
  const navigate = useNavigate();
  const route = useRouteName();
  const main = useRef<HTMLElement>(null);
  const returnTo = useRef<string | null>(null);
  const hasShownScreen = useRef(false);
  const isLoading = state.phase === 'loading';
  const isSignedIn = state.phase === 'signed-in';
  const showsScreen = !isLoading && redirectFor(isSignedIn, route, location.pathname) === null;
  const screenKey = showsScreen ? location.key : null;

  useEffect(() => {
    if (isLoading) return;
    const redirect = redirectFor(isSignedIn, route, location.pathname);
    if (redirect === null) return;
    // Each redirect replaces its history entry, so that Back does not bounce on it.
    if (redirect.to === 'login') {
      returnTo.current = redirect.returnTo;
      void navigate(PATHS.login, { replace: true });
    } else {
      const target = returnTo.current ?? PATHS.home;
      returnTo.current = null;
      void navigate(target, { replace: true });
    }
  }, [isLoading, isSignedIn, route, location.pathname, navigate]);

  // A layout effect, so that the screen's own effects, which run later, can move the focus further.
  useLayoutEffect(() => {
    if (screenKey === null) return;
    // Screen readers start reading the new screen, and Tab continues from there; the first screen keeps the page's.
    if (hasShownScreen.current) main.current?.focus({ preventScroll: true });
    hasShownScreen.current = true;
    window.scrollTo(0, 0);
  }, [screenKey]);

  return (
    <>
      <button type="button" className="skip-link" onClick={() => main.current?.focus()}>
        {t('Skip to content')}
      </button>
      <main className="app-main" id="main" tabIndex={-1} ref={main}>
        {isLoading && <LoadingState />}
        {showsScreen && <Outlet />}
      </main>
    </>
  );
}
