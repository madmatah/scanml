import { type FC, memo, type RefCallback, useId } from 'react';
import { useTranslation } from 'react-i18next';
import type { DocumentWithPages, PageSummary } from '../../../domain/document-details.ts';
import type { PageId, ReadingOrder } from '../../../domain/reading-order.ts';
import { pageShortLabel } from '../../i18next/page-labels.ts';
import { ConfirmDialog } from '../dialogs/confirm-dialog.tsx';
import { PlacementChip } from '../document/placement-chip.tsx';
import { Icon } from '../shell/icon.tsx';
import type { Toasts } from '../shell/toasts.ts';
import { versionedUrl } from '../shell/versioned-url.ts';
import { MoveDialog } from './move-dialog.tsx';
import {
  outsideText,
  pageName,
  placedHeadingText,
  placedHintText,
  selectionStatusText,
  spanLongText,
  spanShortText,
  unplacedHeadingText,
} from './organizer-text.ts';
import { usePageOrganizer } from './use-page-organizer.ts';

export interface PageOrganizerProps {
  readonly document: DocumentWithPages;
  readonly save: (order: ReadingOrder) => Promise<DocumentWithPages>;
  readonly reset: () => Promise<DocumentWithPages>;
  readonly reload: () => void;
  readonly toasts: Toasts;
  readonly onDone: () => void;
}

// aria-disabled rather than disabled, so that a focused button keeps the focus.
const unavailable = (isUnavailable: boolean): 'true' | undefined => {
  return isUnavailable ? 'true' : undefined;
};

// The click on the lists selects, with the keys it holds; the checkbox only shows the selection.
const showsSelectionOnly = (): void => {};

export const PageOrganizer: FC<PageOrganizerProps> = ({ document, save, reset, reload, toasts, onDone }) => {
  const { t } = useTranslation();
  const titleId = useId();
  const {
    organizer,
    toolbar,
    lists,
    indicator,
    title,
    moveButton,
    resetButton,
    announcer,
    cardRef,
    order,
    pages,
    selection,
    isResetting,
    toolbarState,
    groups,
    outsideCount,
    movedPageIds,
    openDialog,
    onClearSelection,
    onSelectSpan,
    onMoveSelection,
    onRestoreOrder,
    onMoveClosed,
    onResetClosed,
  } = usePageOrganizer(document, { save, reset, reload, toasts });

  const renderCards = (pageIds: readonly PageId[], firstIndex: number) => {
    return pageIds.map((pageId, offset) => {
      const page = pages.get(pageId);
      if (page === undefined) return null;
      return (
        <MemoizedOrganizerCard
          key={pageId}
          page={page}
          index={firstIndex + offset}
          total={order.length}
          isSelected={selection.selected.has(pageId)}
          isMoved={movedPageIds.has(pageId)}
          isResetting={isResetting}
          showsUnplaced={groups.hasPlacedPages}
          cardRef={cardRef(pageId)}
        />
      );
    });
  };

  return (
    <section
      ref={organizer}
      className={isResetting ? 'organizer is-busy' : 'organizer'}
      aria-labelledby={titleId}
      aria-busy={unavailable(isResetting)}
    >
      <div ref={toolbar} className="organizer-toolbar">
        <div className="organizer-heading">
          <h3 ref={title} id={titleId} className="organizer-title" tabIndex={-1}>
            {t('Organize pages')}
          </h3>
          <p className="organizer-status">{selectionStatusText(t, toolbarState.selectedCount, order.length)}</p>
          <p className="organizer-saving" hidden={!toolbarState.showsSaving}>
            <span className="spinner" aria-hidden="true" />
            {t('Saving…')}
          </p>
        </div>
        <div className="organizer-actions">
          <button
            type="button"
            className="btn btn-small btn-compact"
            aria-disabled={unavailable(!toolbarState.canClearSelection)}
            onClick={() => {
              if (toolbarState.canClearSelection) onClearSelection();
            }}
          >
            <Icon name="x" />
            <span className="btn-label">{t('Deselect all')}</span>
          </button>
          <button type="button" className="btn btn-small" hidden={!toolbarState.showsSpan} onClick={onSelectSpan}>
            <span className="label-long">{spanLongText(t, toolbarState.spanCount)}</span>
            <span className="label-short">{spanShortText(t, toolbarState.spanCount)}</span>
          </button>
          <button
            ref={moveButton}
            type="button"
            className="btn btn-small"
            aria-disabled={unavailable(!toolbarState.canMoveSelection)}
            onClick={() => {
              if (toolbarState.canMoveSelection) onMoveSelection();
            }}
          >
            <Icon name="move" />
            <span className="label-long">{t('Move selection…')}</span>
            <span className="label-short">{t('Move…')}</span>
          </button>
          <button type="button" className="btn btn-primary btn-small" onClick={onDone}>
            <Icon name="check" />
            {t('Done')}
          </button>
        </div>
      </div>
      <div className="organizer-intro">
        <div className="organizer-help">
          <p className="hint hint-fine-pointer">
            {t(
              'Drag a page to move it: if it is selected, the whole selection follows it. Click: select, Shift+click: range, Ctrl+click: add or remove. Esc cancels a move.',
            )}
          </p>
          <p className="hint hint-coarse-pointer">
            {t(
              'Tap a page to select it, check others, then drag it by the handle (top right of the thumbnail) or after a long press.',
            )}
          </p>
          <p className="hint" hidden={outsideCount === 0}>
            {outsideText(t, outsideCount)}
          </p>
        </div>
        <button
          ref={resetButton}
          type="button"
          className="btn btn-small"
          hidden={!toolbarState.showsReset}
          aria-disabled={unavailable(!toolbarState.canReset)}
          onClick={() => {
            if (toolbarState.canReset) onRestoreOrder();
          }}
        >
          <Icon name="undo" />
          {t('Restore automatic order')}
        </button>
      </div>
      <div ref={lists} className="organizer-lists">
        <section className="organizer-group">
          <div className="page-group-header">
            <h4 className="page-group-title">{placedHeadingText(t, groups.placed.length)}</h4>
            <p className="page-group-hint">{placedHintText(t, order.length, groups.hasPlacedPages)}</p>
          </div>
          {/* biome-ignore lint/a11y/noRedundantRoles: Safari drops the role of a list drawn without its markers. */}
          <ol className="page-grid organizer-grid" role="list">
            {renderCards(groups.placed, 0)}
          </ol>
        </section>
        <section className="organizer-group" hidden={groups.unplaced.length === 0}>
          <div className="page-group-header">
            <h4 className="page-group-title">{unplacedHeadingText(t, groups.unplaced.length)}</h4>
            <p className="page-group-hint">
              {t('Nothing tells where they go: they are at the end of the document. Drag them to their place.')}
            </p>
          </div>
          {/* biome-ignore lint/a11y/noRedundantRoles: Safari drops the role of a list drawn without its markers. */}
          <ol className="page-grid organizer-grid" role="list">
            {renderCards(groups.unplaced, groups.placed.length)}
          </ol>
        </section>
        <span ref={indicator} className="drop-indicator" hidden aria-hidden="true" />
      </div>
      <p ref={announcer} className="visually-hidden" aria-live="polite" />
      {openDialog?.kind === 'move' && (
        <MoveDialog
          count={openDialog.moving.length}
          choices={openDialog.choices}
          onClosed={(target) => onMoveClosed(openDialog.moving, target)}
        />
      )}
      {openDialog?.kind === 'reset' && (
        <ConfirmDialog
          title={t('Restore automatic order?')}
          message={t(
            'The pages will go back to the place given by their number or by their photo series. Moves made by hand will be forgotten.',
          )}
          confirmLabel={t('Restore automatic order')}
          onClosed={onResetClosed}
        />
      )}
    </section>
  );
};

interface OrganizerCardProps {
  readonly page: PageSummary;
  readonly index: number;
  readonly total: number;
  readonly isSelected: boolean;
  readonly isMoved: boolean;
  readonly isResetting: boolean;
  readonly showsUnplaced: boolean;
  readonly cardRef: RefCallback<HTMLLIElement>;
}

const OrganizerCard: FC<OrganizerCardProps> = ({
  page,
  index,
  total,
  isSelected,
  isMoved,
  isResetting,
  showsUnplaced,
  cardRef,
}) => {
  const { t } = useTranslation();
  const name = pageName(t, page, index);
  const pageId = page.id;
  const classes = ['organizer-card', isSelected && 'is-selected', isMoved && 'is-moved'];
  return (
    <li ref={cardRef} className={classes.filter(Boolean).join(' ')} data-id={pageId}>
      <div className="organizer-card-frame">
        <span className="page-thumb">
          {/* The api draws the thumbnail of a rotated page again at the same address. */}
          <img
            src={versionedUrl(page.thumbnailUrl, String(page.rotation))}
            alt=""
            loading="lazy"
            decoding="async"
            draggable={false}
          />
          <span className="organizer-index" aria-hidden="true">
            {String(index + 1)}
          </span>
          <span className="drag-handle" title={t('Drag to move')} aria-hidden="true">
            <Icon name="grip" />
          </span>
          <label className="organizer-check">
            <input
              type="checkbox"
              name="selected-pages"
              value={pageId}
              checked={isSelected}
              onChange={showsSelectionOnly}
              aria-label={t('Select {{page}}', { page: name })}
            />
          </label>
        </span>
        <span className="page-card-body">
          <span className="page-card-label">{pageShortLabel(t, { page_label: page.pageLabel })}</span>
          <PlacementChip page={page} showsUnplaced={showsUnplaced} />
        </span>
        <span className="organizer-steps">
          <button
            type="button"
            className="btn btn-icon btn-small"
            title={t('Place before the previous one')}
            data-step="-1"
            aria-label={t('Place {{page}} before the previous one', { page: name })}
            aria-disabled={unavailable(index === 0 || isResetting)}
          >
            <Icon name="chevron-left" />
          </button>
          <button
            type="button"
            className="btn btn-icon btn-small"
            title={t('Place after the next one')}
            data-step="1"
            aria-label={t('Place {{page}} after the next one', { page: name })}
            aria-disabled={unavailable(index === total - 1 || isResetting)}
          >
            <Icon name="chevron-right" />
          </button>
        </span>
      </div>
    </li>
  );
};

const MemoizedOrganizerCard = memo(OrganizerCard);
