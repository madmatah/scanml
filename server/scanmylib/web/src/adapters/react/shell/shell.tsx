import type { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet } from 'react-router';

import type { Clipboard } from '../../../application/clipboard.ts';
import type { DocumentCatalog } from '../../../application/document-catalog.ts';
import type { DocumentStore } from '../../../application/document-store.ts';
import type { EngineStatus } from '../../../application/engine-status.ts';
import type { PageStore } from '../../../application/page-store.ts';
import type { PairingSource } from '../../../application/pairing-source.ts';
import type { Scheduler } from '../../../application/scheduler.ts';
import type { Session } from '../../../application/session.ts';
import type { UploadQueue } from '../../../application/upload-queue.ts';
import type { UuidSource } from '../../../application/uuid-source.ts';
import type { DateFormatting, NumberFormatting } from '../../../domain/formatting.ts';
import { ConfirmDialog } from '../dialogs/confirm-dialog.tsx';
import { EngineBanners } from '../engine-status/engine-banners.tsx';
import type { FormulaTypesetter } from '../sanitized-html/use-sanitized-html.ts';
import { Header } from './header.tsx';
import { LoadingState } from './loading-state.tsx';
import { ToastRegion } from './toast-region.tsx';
import type { Toasts } from './toasts.ts';
import { useShell } from './use-shell.ts';

export interface ShellServices {
  readonly session: Session;
  readonly toasts: Toasts;
  readonly engineStatus: EngineStatus;
  readonly formatting: NumberFormatting;
  readonly dates: DateFormatting;
  readonly catalog: DocumentCatalog;
  readonly documents: DocumentStore;
  readonly pages: PageStore;
  readonly scheduler: Scheduler;
  readonly uuids: UuidSource;
  readonly pairing: PairingSource;
  readonly clipboard: Clipboard;
  readonly uploads: UploadQueue<File>;
  readonly typesetFormulas: FormulaTypesetter;
}

export const Shell: FC<{ readonly services: ShellServices }> = ({ services }) => {
  const { t } = useTranslation();
  const shell = useShell(services.session, services.toasts, services.engineStatus, services.uploads);
  return (
    <>
      <button type="button" className="skip-link" onClick={shell.onSkipToContent}>
        {t('Skip to content')}
      </button>
      <Header
        isSignedIn={shell.isSignedIn}
        section={shell.section}
        currentPath={shell.currentPath}
        engine={shell.engine}
        formatting={services.formatting}
        isEnginePanelOpen={shell.isEnginePanelOpen}
        onToggleEnginePanel={shell.onToggleEnginePanel}
        onCloseEnginePanel={shell.onCloseEnginePanel}
        onSignOut={shell.onSignOut}
      />
      <EngineBanners engine={shell.engine} />
      <main className="app-main" id="main" tabIndex={-1} ref={shell.main}>
        {shell.isLoading && <LoadingState />}
        {/* The engine's polls and the toasts render the shell again, not the screen: the outlet gives the router's
            element, the same at each render of the shell, which React skips. */}
        {shell.showsScreen && <Outlet />}
      </main>
      <ToastRegion shownToasts={shell.shownToasts} onDismiss={shell.onDismissToast} />
      {shell.isConfirmingSignOut && (
        <ConfirmDialog
          title={t('Sign out now?')}
          message={t('Photos are still being uploaded: they will fail if you sign out.')}
          confirmLabel={t('Sign out')}
          isDanger
          onClosed={shell.onSignOutClosed}
        />
      )}
    </>
  );
};
