import { useEffect, useLayoutEffect, useRef, useSyncExternalStore } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useLocation, useMatches, useNavigate } from 'react-router';

import type { Session } from '../../../application/session.ts';
import { errorMessage } from './error-message.ts';
import { Header } from './header.tsx';
import { LoadingState } from './loading-state.tsx';
import { type Access, isRouteName, PATHS, type RouteName, redirectFor, sectionOf } from './navigation.ts';
import { ToastRegion } from './toast-region.tsx';
import type { Toasts } from './toasts.ts';

export interface ShellServices {
  readonly session: Session;
  readonly toasts: Toasts;
}

function useRouteName(): RouteName {
  const id = useMatches().at(-1)?.id ?? 'unknown';
  return isRouteName(id) ? id : 'unknown';
}

export function Shell({ services }: { readonly services: ShellServices }) {
  const { session, toasts } = services;
  const { t } = useTranslation();
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot);
  const location = useLocation();
  const navigate = useNavigate();
  const route = useRouteName();
  const main = useRef<HTMLElement>(null);
  const returnTo = useRef<string | null>(null);
  const hasShownScreen = useRef(false);
  const hasJustSignedOut = useRef(false);
  const isLoading = state.phase === 'loading';
  const isSignedIn = state.phase === 'signed-in';
  const showsScreen =
    !isLoading && redirectFor(isSignedIn ? 'signed-in' : 'signed-out', route, location.pathname) === null;
  const screenKey = showsScreen ? location.key : null;

  useEffect(() => {
    if (isLoading) return;
    let access: Access = 'signed-in';
    if (!isSignedIn) access = hasJustSignedOut.current ? 'just-signed-out' : 'signed-out';
    const redirect = redirectFor(access, route, location.pathname);
    if (redirect === null) return;
    if (redirect.to === 'login') {
      hasJustSignedOut.current = false;
      returnTo.current = redirect.returnTo;
      void navigate(PATHS.login, { replace: redirect.replacesEntry });
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

  async function signOut(): Promise<void> {
    hasJustSignedOut.current = true;
    try {
      await session.signOut();
    } catch (failure) {
      hasJustSignedOut.current = false;
      toasts.show(errorMessage(t, failure, t('Could not sign out.')), 'error');
    }
  }

  return (
    <>
      <button type="button" className="skip-link" onClick={() => main.current?.focus()}>
        {t('Skip to content')}
      </button>
      <Header
        isSignedIn={isSignedIn}
        section={sectionOf(route)}
        onSignOut={() => {
          // signOut handles its own failures, so its promise never rejects.
          void signOut();
        }}
      />
      <main className="app-main" id="main" tabIndex={-1} ref={main}>
        {isLoading && <LoadingState />}
        {showsScreen && <Outlet />}
      </main>
      <ToastRegion toasts={toasts} />
    </>
  );
}
