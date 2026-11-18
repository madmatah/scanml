import { useEffect, useLayoutEffect, useRef, useSyncExternalStore } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useLocation, useMatches, useNavigate } from 'react-router';

import type { Clipboard } from '../../../application/clipboard.ts';
import type { DocumentCatalog } from '../../../application/document-catalog.ts';
import type { DocumentStore } from '../../../application/document-store.ts';
import type { EngineStatus } from '../../../application/engine-status.ts';
import type { PairingSource } from '../../../application/pairing-source.ts';
import type { Scheduler } from '../../../application/scheduler.ts';
import type { Session } from '../../../application/session.ts';
import type { UuidSource } from '../../../application/uuid-source.ts';
import type { DateFormatting, NumberFormatting } from '../../../domain/formatting.ts';
import { EngineBanners } from '../engine-status/engine-banners.tsx';
import { errorMessage } from './error-message.ts';
import { Header } from './header.tsx';
import { LoadingState } from './loading-state.tsx';
import { type Access, PATHS, type RouteName, redirectFor, routeNameOf, sectionOf } from './navigation.ts';
import { ToastRegion } from './toast-region.tsx';
import type { Toasts } from './toasts.ts';

export interface ShellServices {
  readonly session: Session;
  readonly toasts: Toasts;
  readonly engineStatus: EngineStatus;
  readonly formatting: NumberFormatting;
  readonly dates: DateFormatting;
  readonly catalog: DocumentCatalog;
  readonly documents: DocumentStore;
  readonly scheduler: Scheduler;
  readonly uuids: UuidSource;
  readonly pairing: PairingSource;
  readonly clipboard: Clipboard;
}

function useRouteName(): RouteName {
  const match = useMatches().at(-1);
  return match === undefined ? 'unknown' : routeNameOf(match.id, match.params.documentId);
}

export function Shell({ services }: { readonly services: ShellServices }) {
  const { session, toasts, engineStatus, formatting } = services;
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
        engineStatus={engineStatus}
        formatting={formatting}
        onSignOut={() => {
          // signOut handles its own failures, so its promise never rejects.
          void signOut();
        }}
      />
      <EngineBanners engineStatus={engineStatus} />
      <main className="app-main" id="main" tabIndex={-1} ref={main}>
        {isLoading && <LoadingState />}
        {showsScreen && <Outlet />}
      </main>
      <ToastRegion toasts={toasts} />
    </>
  );
}
