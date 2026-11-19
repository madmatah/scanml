import { type RefObject, useCallback, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useMatches, useNavigate } from 'react-router';

import type { EngineStatus, EngineStatusState } from '../../../application/engine-status.ts';
import type { Session } from '../../../application/session.ts';
import { hasFailures, type UploadQueue } from '../../../application/upload-queue.ts';
import { settledUploadsText } from '../uploads/upload-text.ts';
import { errorMessage } from './error-message.ts';
import {
  NO_RETURN_MEMORY,
  navigationFor,
  type ReturnMemory,
  type RouteName,
  redirectFor,
  routeNameOf,
  type Section,
  sectionOf,
} from './navigation.ts';
import type { Toast, Toasts } from './toasts.ts';

export interface ShellState {
  readonly isLoading: boolean;
  readonly isSignedIn: boolean;
  readonly showsScreen: boolean;
  readonly section: Section | null;
  readonly currentPath: string;
  readonly engine: EngineStatusState;
  readonly shownToasts: readonly Toast[];
  readonly isEnginePanelOpen: boolean;
  readonly isConfirmingSignOut: boolean;
  readonly main: RefObject<HTMLElement | null>;
  readonly onSkipToContent: () => void;
  readonly onSignOut: () => void;
  readonly onSignOutClosed: (isConfirmed: boolean) => void;
  readonly onToggleEnginePanel: () => void;
  readonly onCloseEnginePanel: () => void;
  readonly onDismissToast: (id: number) => void;
}

const useRouteName = (): RouteName => {
  const match = useMatches().at(-1);
  return match === undefined ? 'unknown' : routeNameOf(match.id, match.params);
};

export const useShell = (
  session: Session,
  toasts: Toasts,
  engineStatus: EngineStatus,
  uploads: UploadQueue<File>,
): ShellState => {
  const { t } = useTranslation();
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot);
  const engine = useSyncExternalStore(engineStatus.subscribe, engineStatus.getSnapshot);
  const shownToasts = useSyncExternalStore(toasts.subscribe, toasts.getSnapshot);
  const location = useLocation();
  const navigate = useNavigate();
  const route = useRouteName();
  const main = useRef<HTMLElement>(null);
  const returnMemory = useRef<ReturnMemory>(NO_RETURN_MEMORY);
  const hasShownScreen = useRef(false);
  const [isConfirmingSignOut, setConfirmingSignOut] = useState(false);
  const [isEnginePanelOpen, setEnginePanelOpen] = useState(false);
  const isLoading = state.phase === 'loading';
  const isSignedIn = state.phase === 'signed-in';
  const showsScreen =
    !isLoading && redirectFor(isSignedIn ? 'signed-in' : 'signed-out', route, location.pathname) === null;
  const screenKey = showsScreen ? location.key : null;

  useEffect(() => {
    if (isLoading) return;
    const { navigation, memory } = navigationFor(returnMemory.current, isSignedIn, route, location.pathname);
    returnMemory.current = memory;
    if (navigation !== null) void navigate(navigation.path, { replace: navigation.replacesEntry });
  }, [isLoading, isSignedIn, route, location.pathname, navigate]);

  // Uploads go on from one screen to the next: their outcome is told wherever the user is.
  useEffect(
    () =>
      uploads.watchSettled((settled) => {
        toasts.show(settledUploadsText(t, settled), hasFailures(settled) ? 'error' : 'success');
      }),
    [uploads, toasts, t],
  );

  // A layout effect, so that the screen's own effects, which run later, can move the focus further.
  useLayoutEffect(() => {
    if (screenKey === null) return;
    // Screen readers start reading the new screen, and Tab continues from there; the first screen keeps the page's.
    if (hasShownScreen.current) main.current?.focus({ preventScroll: true });
    hasShownScreen.current = true;
    window.scrollTo(0, 0);
  }, [screenKey]);

  // The same function at each render, so that the open panel's listeners, which close it, stay as they were added.
  const closeEnginePanel = useCallback(() => setEnginePanelOpen(false), []);

  const signOut = async (): Promise<void> => {
    returnMemory.current = { ...returnMemory.current, hasJustSignedOut: true };
    try {
      await session.signOut();
    } catch (failure) {
      returnMemory.current = { ...returnMemory.current, hasJustSignedOut: false };
      toasts.show(errorMessage(t, failure, t('Could not sign out.')), 'error');
    }
  };

  return {
    isLoading,
    isSignedIn,
    showsScreen,
    section: sectionOf(route),
    currentPath: location.pathname,
    engine,
    shownToasts,
    isEnginePanelOpen,
    isConfirmingSignOut,
    main,
    onSkipToContent: () => main.current?.focus(),
    onSignOut: () => {
      // The photos still being sent would fail once the session ends.
      if (uploads.isBusy()) setConfirmingSignOut(true);
      // signOut handles its own failures, so its promise never rejects.
      else void signOut();
    },
    onSignOutClosed: (isConfirmed) => {
      setConfirmingSignOut(false);
      // signOut handles its own failures, so its promise never rejects.
      if (isConfirmed) void signOut();
    },
    onToggleEnginePanel: () => setEnginePanelOpen(!isEnginePanelOpen),
    onCloseEnginePanel: closeEnginePanel,
    onDismissToast: (id) => toasts.dismiss(id),
  };
};
