import type { TFunction } from 'i18next';
import { type FC, type FormEvent, type ReactNode, useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router';

import type { Clipboard } from '../../../application/clipboard.ts';
import { isNotFound } from '../../../application/document-loader.ts';
import type { DocumentStore } from '../../../application/document-store.ts';
import {
  createPageActions,
  type PageAction,
  type PageActionOutcome,
  type PageDeletion,
} from '../../../application/page-actions.ts';
import { createPageLoader, type PageLoad, type PageLoader } from '../../../application/page-loader.ts';
import type { PageStore } from '../../../application/page-store.ts';
import type { Scheduler } from '../../../application/scheduler.ts';
import { groupPages, hasPlacedPages, type PageSummary } from '../../../domain/document-details.ts';
import type { DateFormatting, NumberFormatting } from '../../../domain/formatting.ts';
import {
  isBeingRead,
  type PageDetails,
  type PageNeighbors,
  pageNeighbors,
  readPageNumberEntry,
  turnedLeft,
  turnedRight,
  typedNumberOf,
} from '../../../domain/page-details.ts';
import { numberSourceLabel, pageShortLabel, pageStatusLabel, pageTitle } from '../../i18next/page-labels.ts';
import { ConfirmDialog } from '../dialogs/confirm-dialog.tsx';
import { PlacementChip, shownPlacement } from '../document/placement-chip.tsx';
import type { FormulaTypesetter } from '../sanitized-html/use-sanitized-html.ts';
import { errorMessage } from '../shell/error-message.ts';
import { ErrorState } from '../shell/error-state.tsx';
import { Icon, type IconName } from '../shell/icon.tsx';
import { LoadingState } from '../shell/loading-state.tsx';
import { documentPath, documentTitle, idOfAddress, PATHS, pagePath } from '../shell/navigation.ts';
import type { Toasts } from '../shell/toasts.ts';
import { detailRows, numberHelp } from './page-text.ts';
import { ScanPane } from './scan-pane.tsx';
import { TextPane } from './text-pane.tsx';

export interface PageScreenProps {
  readonly pages: PageStore;
  readonly documents: Pick<DocumentStore, 'readDocument'>;
  readonly scheduler: Scheduler;
  readonly toasts: Toasts;
  readonly clipboard: Clipboard;
  readonly formatting: NumberFormatting;
  readonly dates: DateFormatting;
  readonly typesetFormulas: FormulaTypesetter;
}

// Each page has a screen of its own, so that going to the previous or the next page starts the next one afresh.
export const PageScreen: FC<PageScreenProps> = (props) => {
  const pageId = idOfAddress(useParams().pageId);
  if (pageId === null) return null;
  return <PageView key={pageId} pageId={pageId} {...props} />;
};

interface PageViewProps extends PageScreenProps {
  readonly pageId: string;
}

const isTypingTarget = (target: EventTarget | null): boolean => {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable ||
      target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.tagName === 'SELECT')
  );
};

const actionSuccessMessage = (t: TFunction, action: PageAction): string => {
  switch (action.kind) {
    case 'saveNumber':
      return t('Number {{number}} saved.', { number: action.number });
    case 'clearNumber':
      return t('Manual number cleared.');
    case 'rotate':
      return t('Page rotated: its text will be read again.');
    case 'setExclusion':
      return action.isExcluded ? t('Page excluded from the document.') : t('Page put back in the document.');
    case 'readAgain':
      return t('The text of this page will be read again.');
  }
};

const PageView: FC<PageViewProps> = ({
  pageId,
  pages,
  documents,
  scheduler,
  toasts,
  clipboard,
  formatting,
  dates,
  typesetFormulas,
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [load, setLoad] = useState<PageLoad>({ phase: 'loading' });
  const [isBusy, setBusy] = useState(false);
  const [isConfirmingDelete, setConfirmingDelete] = useState(false);
  const loader = useRef<PageLoader | null>(null);
  const [actions] = useState(() =>
    createPageActions({
      pageId,
      pages,
      reload: async () => {
        await loader.current?.load();
      },
      onBusyChange: setBusy,
    }),
  );
  const screenTitle = load.phase === 'loaded' ? `${pageTitle(t, load.page)} · ${load.document.title}` : null;
  const neighbors = load.phase === 'loaded' ? pageNeighbors(load.document.pages, load.page.id) : null;
  const previousId = neighbors?.previous?.id ?? null;
  const nextId = neighbors?.next?.id ?? null;

  // The title of the previous screen stays until the page's own is known.
  useEffect(() => {
    if (screenTitle !== null) document.title = documentTitle(screenTitle);
  }, [screenTitle]);

  useEffect(() => {
    const leaving = new AbortController();
    const pageLoader = createPageLoader({
      readPage: (signal) => pages.readPage(pageId, signal),
      readDocument: (documentId, signal) => documents.readDocument(documentId, signal),
      readPageHtml: (signal) => pages.readPageHtml(pageId, signal),
      scheduler,
      leaving: leaving.signal,
      onChange: setLoad,
      onRefreshFailed: (failure) => toasts.show(errorMessage(t, failure, t('Could not refresh the page.')), 'error'),
    });
    loader.current = pageLoader;
    void pageLoader.load();
    return () => leaving.abort();
  }, [pageId, pages, documents, scheduler, toasts, t]);

  useEffect(() => {
    const goToNeighbor = (event: KeyboardEvent): void => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (isTypingTarget(event.target) || document.querySelector('dialog[open]') !== null) return;
      const targetId = event.key === 'ArrowLeft' ? previousId : event.key === 'ArrowRight' ? nextId : null;
      if (targetId === null) return;
      event.preventDefault();
      void navigate(pagePath(targetId));
    };
    document.addEventListener('keydown', goToNeighbor);
    return () => document.removeEventListener('keydown', goToNeighbor);
  }, [previousId, nextId, navigate]);

  const tellOutcome = (outcome: PageActionOutcome): void => {
    if (outcome.kind === 'succeeded') toasts.show(actionSuccessMessage(t, outcome.action), 'success');
    else toasts.show(errorMessage(t, outcome.failure, t('Action failed.')), 'error');
  };

  const runAction = (action: PageAction): void => {
    // The actions tell their outcome, failures included, so their promise never rejects.
    void actions.run(action, tellOutcome);
  };

  const deletePage = (page: PageDetails, destination: PageSummary | null): void => {
    const tellDeletion = (deletion: PageDeletion): void => {
      if (deletion.kind === 'failed') {
        toasts.show(errorMessage(t, deletion.failure, t('Could not delete.')), 'error');
        return;
      }
      toasts.show(t('Page deleted.'), 'success');
      void navigate(destination === null ? documentPath(page.documentId) : pagePath(destination.id), { replace: true });
    };
    // The deletion tells its outcome, its failure included, so its promise never rejects.
    void actions.deletePage(tellDeletion);
  };

  if (load.phase === 'loading') {
    return (
      <section className="view page-view">
        <LoadingState />
      </section>
    );
  }
  if (load.phase === 'failed') {
    const isMissing = isNotFound(load.failure);
    return (
      <section className="view page-view">
        <ErrorState
          title={isMissing ? t('Page not found') : t('Could not load')}
          message={isMissing ? t('This page does not exist or has been deleted.') : errorMessage(t, load.failure)}
          {...(isMissing ? {} : { onRetry: () => void loader.current?.load() })}
          actions={
            <Link className="btn" to={PATHS.home}>
              {t('Back to the library')}
            </Link>
          }
        />
      </section>
    );
  }

  const { page, document: shownDocument, sanitizedHtml } = load;
  const shownNeighbors = neighbors ?? { previous: null, next: null, position: null };
  return (
    <section className="view page-view">
      <nav className="breadcrumb" aria-label={t('Breadcrumb')}>
        <Link to={PATHS.home}>{t('Library')}</Link>
        <span className="breadcrumb-separator" aria-hidden="true">
          ›
        </span>
        <Link to={documentPath(shownDocument.id)}>{shownDocument.title}</Link>
        <span className="breadcrumb-separator" aria-hidden="true">
          ›
        </span>
        <span aria-current="page">{pageTitle(t, page)}</span>
      </nav>
      <PageHeader page={page} documentPages={shownDocument.pages} neighbors={shownNeighbors} />
      <PageNotices page={page} />
      <PageToolbar
        page={page}
        isBusy={isBusy}
        onSaveNumber={(number) => runAction({ kind: 'saveNumber', number })}
        onInvalidNumber={() => toasts.show(t('Enter a whole page number between 1 and 9999.'), 'error')}
        onClearNumber={() => runAction({ kind: 'clearNumber' })}
        onRotate={(rotation) => runAction({ kind: 'rotate', rotation })}
        onExclude={(isExcluded) => runAction({ kind: 'setExclusion', isExcluded })}
        onReadAgain={() => runAction({ kind: 'readAgain' })}
        onDelete={() => setConfirmingDelete(true)}
      />
      <div className="page-split">
        <ScanPane page={page} />
        <TextPane
          page={page}
          sanitizedHtml={sanitizedHtml}
          typesetFormulas={typesetFormulas}
          clipboard={clipboard}
          toasts={toasts}
        />
      </div>
      <details className="card page-details">
        <summary>{t('Technical details')}</summary>
        <dl className="details-list">
          {detailRows(t, page, { numbers: formatting, dates }).map(({ term, description, isCode }) => (
            <div key={term}>
              <dt>{term}</dt>
              <dd>{isCode ? <code>{description}</code> : description}</dd>
            </div>
          ))}
        </dl>
      </details>
      {isConfirmingDelete && (
        <ConfirmDialog
          title={t('Delete this page?')}
          message={t(
            'The scan, its text and its illustrations will be moved to the library’s trash (.trash), then the document will be reassembled.',
          )}
          confirmLabel={t('Delete page')}
          isDanger
          onClosed={(isConfirmed) => {
            setConfirmingDelete(false);
            if (isConfirmed) deletePage(page, shownNeighbors.next ?? shownNeighbors.previous);
          }}
        />
      )}
    </section>
  );
};

interface PageHeaderProps {
  readonly page: PageDetails;
  readonly documentPages: readonly PageSummary[];
  readonly neighbors: PageNeighbors;
}

const PageHeader: FC<PageHeaderProps> = ({ page, documentPages, neighbors }) => {
  const { t } = useTranslation();
  const source = numberSourceLabel(t, page.numberSource);
  const status = pageStatusLabel(t, page.status);
  const showsUnplaced = hasPlacedPages(groupPages(documentPages));
  const { position } = neighbors;
  return (
    <header className="page-header">
      <div className="page-heading">
        <h1 tabIndex={-1}>{pageTitle(t, page)}</h1>
        {/* biome-ignore lint/a11y/noRedundantRoles: Safari drops the role of a list drawn without its markers. */}
        <ul className="chips" role="list">
          {source !== null && (
            <li className={`chip chip-source source-${page.numberSource}`} title={source.description}>
              {source.label}
            </li>
          )}
          <li className={`chip chip-${status.tone}`}>{status.label}</li>
          {page.isExcluded && <li className="chip chip-outline">{t('Excluded', { context: 'one page' })}</li>}
          {page.duplicateOf !== null && page.duplicateOf !== '' && <li className="chip chip-warn">{t('Duplicate')}</li>}
          {shownPlacement(t, page, showsUnplaced) !== null && (
            <li>
              <PlacementChip page={page} showsUnplaced={showsUnplaced} />
            </li>
          )}
        </ul>
      </div>
      <nav className="pager" aria-label={t('Document pages')}>
        <NeighborLink neighbor={neighbors.previous} rel="prev">
          <Icon name="chevron-left" />
          <span className="btn-label">{t('Previous')}</span>
        </NeighborLink>
        <span className="pager-position">{position === null ? '' : `${position.index + 1} / ${position.count}`}</span>
        <NeighborLink neighbor={neighbors.next} rel="next">
          <span className="btn-label">{t('Next')}</span>
          <Icon name="chevron-right" />
        </NeighborLink>
      </nav>
    </header>
  );
};

interface NeighborLinkProps {
  readonly neighbor: PageSummary | null;
  readonly rel: 'prev' | 'next';
  readonly children: ReactNode;
}

const NeighborLink: FC<NeighborLinkProps> = ({ neighbor, rel, children }) => {
  const { t } = useTranslation();
  if (neighbor === null) {
    return (
      // biome-ignore lint/a11y/useValidAnchor: a link with nowhere to go, marked as such, keeps its place in the pager.
      <a className="btn" rel={rel} aria-disabled="true">
        {children}
      </a>
    );
  }
  return (
    <Link
      className="btn"
      rel={rel}
      to={pagePath(neighbor.id)}
      title={pageShortLabel(t, { page_label: neighbor.pageLabel })}
    >
      {children}
    </Link>
  );
};

const PageNotices: FC<{ readonly page: PageDetails }> = ({ page }) => {
  const { t } = useTranslation();
  const hasError = page.status === 'error';
  const isDuplicate = page.duplicateOf !== null && page.duplicateOf !== '';
  return (
    <div className="page-notices" hidden={!hasError && !isDuplicate && !page.isExcluded}>
      {hasError && (
        <div className="notice notice-danger">
          <Icon name="alert" />
          <p>
            <strong>{t('Couldn’t read the text.')}</strong> {t('You can read the text again or rotate the page.')}
            {page.error !== null && page.error !== '' && (
              <span className="notice-detail">{t('Details: {{error}}', { error: page.error })}</span>
            )}
          </p>
        </div>
      )}
      {isDuplicate && page.duplicateOf !== null && (
        <div className="notice notice-warn">
          <Icon name="copy" />
          <p>
            <strong>{t('Duplicate.')}</strong> {t('A newer scan has the same number and replaces it in the document.')}{' '}
            <Link to={pagePath(page.duplicateOf)}>{t('See the page kept')}</Link>
          </p>
        </div>
      )}
      {page.isExcluded && (
        <div className="notice">
          <Icon name="eye-off" />
          <p>
            <strong>{t('Page excluded.')}</strong> {t('It does not appear in document.md.')}
          </p>
        </div>
      )}
    </div>
  );
};

interface PageToolbarProps {
  readonly page: PageDetails;
  readonly isBusy: boolean;
  readonly onSaveNumber: (number: number) => void;
  readonly onInvalidNumber: () => void;
  readonly onClearNumber: () => void;
  readonly onRotate: (rotation: number) => void;
  readonly onExclude: (isExcluded: boolean) => void;
  readonly onReadAgain: () => void;
  readonly onDelete: () => void;
}

const PageToolbar: FC<PageToolbarProps> = ({
  page,
  isBusy,
  onSaveNumber,
  onInvalidNumber,
  onClearNumber,
  onRotate,
  onExclude,
  onReadAgain,
  onDelete,
}) => {
  const { t } = useTranslation();
  const numberId = useId();
  const numberHelpId = useId();
  const rotateLabelId = useId();
  const numberInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const input = numberInput.current;
    if (input === null || document.activeElement === input) return;
    const typedNumber = typedNumberOf(page);
    input.value = typedNumber === null ? '' : String(typedNumber);
  }, [page]);

  const saveNumber = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const input = numberInput.current;
    if (isBusy || input === null) return;
    const entry = readPageNumberEntry(input.value);
    if (entry.isValid) {
      onSaveNumber(entry.number);
    } else {
      onInvalidNumber();
      input.focus();
    }
  };

  return (
    <section className="card page-toolbar" aria-label={t('Page actions')}>
      <form className="number-form" noValidate onSubmit={saveNumber}>
        <label htmlFor={numberId} className="field-label">
          {t('Page number')}
        </label>
        <div className="number-controls">
          <input
            ref={numberInput}
            id={numberId}
            type="number"
            inputMode="numeric"
            min={1}
            max={9999}
            step={1}
            className="input input-number"
            aria-describedby={numberHelpId}
          />
          <button type="submit" className="btn" aria-disabled={isBusy ? 'true' : undefined}>
            <Icon name="check" />
            {t('Save')}
          </button>
          <ActionButton
            className="btn btn-ghost"
            isUnavailable={isBusy || page.manualNumber === null}
            onActivate={onClearNumber}
          >
            {t('Clear')}
          </ActionButton>
        </div>
        <p id={numberHelpId} className="hint">
          {numberHelp(t, page)}
        </p>
      </form>
      <div className="button-row page-actions">
        {/* biome-ignore lint/a11y/useSemanticElements: a fieldset would draw its own border and margins in the row. */}
        <div className="rotate-group" role="group" aria-labelledby={rotateLabelId}>
          <span id={rotateLabelId} className="rotate-group-label">
            {t('Rotate')}
          </span>
          <IconButton
            iconName="rotate-left"
            label={t('Rotate 90° to the left')}
            isUnavailable={isBusy}
            onActivate={() => onRotate(turnedLeft(page.rotation))}
          />
          <IconButton
            iconName="rotate-right"
            label={t('Rotate 90° to the right')}
            isUnavailable={isBusy}
            onActivate={() => onRotate(turnedRight(page.rotation))}
          />
        </div>
        <ActionButton className="btn" isUnavailable={isBusy} onActivate={() => onExclude(!page.isExcluded)}>
          <Icon name={page.isExcluded ? 'eye' : 'eye-off'} />
          <span className="label-long">
            {page.isExcluded ? t('Put back in the document') : t('Exclude from the document')}
          </span>
          <span className="label-short">{page.isExcluded ? t('Put back') : t('Exclude')}</span>
        </ActionButton>
        <ActionButton className="btn" isUnavailable={isBusy || isBeingRead(page.status)} onActivate={onReadAgain}>
          <Icon name="refresh" />
          {t('Read the text again')}
        </ActionButton>
        <ActionButton className="btn btn-danger" isUnavailable={isBusy} onActivate={onDelete}>
          <Icon name="trash" />
          {t('Delete')}
        </ActionButton>
      </div>
    </section>
  );
};

interface ActionButtonProps {
  readonly className: string;
  // Marked aria-disabled rather than disabled: a disabled button loses the focus, which would leave the button just
  // used.
  readonly isUnavailable: boolean;
  readonly onActivate: () => void;
  readonly children: ReactNode;
}

const ActionButton: FC<ActionButtonProps> = ({ className, isUnavailable, onActivate, children }) => {
  return (
    <button
      type="button"
      className={className}
      aria-disabled={isUnavailable ? 'true' : undefined}
      onClick={() => {
        if (!isUnavailable) onActivate();
      }}
    >
      {children}
    </button>
  );
};

interface IconButtonProps {
  readonly iconName: IconName;
  readonly label: string;
  readonly isUnavailable: boolean;
  readonly onActivate: () => void;
}

const IconButton: FC<IconButtonProps> = ({ iconName, label, isUnavailable, onActivate }) => {
  return (
    <button
      type="button"
      className="btn btn-icon"
      aria-label={label}
      title={label}
      aria-disabled={isUnavailable ? 'true' : undefined}
      onClick={() => {
        if (!isUnavailable) onActivate();
      }}
    >
      <Icon name={iconName} />
    </button>
  );
};
