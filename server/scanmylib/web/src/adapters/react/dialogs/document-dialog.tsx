import { useId } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';

import type { DocumentFields } from '../../../application/document-catalog.ts';
import { documentKindChoices } from '../../i18next/document-labels.ts';
import type { EditedDocument } from './document-form.ts';
import { useDocumentDialog } from './use-document-dialog.ts';

export interface DocumentDialogProps<Saved> {
  readonly heading: string;
  readonly submitLabel: string;
  readonly initial?: EditedDocument;
  readonly showsNotes?: boolean;
  readonly onSubmit: (fields: DocumentFields) => Promise<Saved>;
  readonly onClosed: (saved: Saved | null) => void;
}

const TEXT_MAXIMUM_LENGTH = 300;
const NOTES_MAXIMUM_LENGTH = 20_000;
const NOTES_ROWS = 3;

export const DocumentDialog = <Saved,>({
  heading,
  submitLabel,
  initial,
  showsNotes = false,
  onSubmit,
  onClosed,
}: DocumentDialogProps<Saved>) => {
  const { t } = useTranslation();
  const ids = { heading: useId(), title: useId(), author: useId(), notes: useId(), unwarpHint: useId() };
  const {
    dialog,
    titleInput,
    form,
    error,
    isBusy,
    onTitleChange,
    onAuthorChange,
    onKindChange,
    onUnwarpChange,
    onNotesChange,
    onFormSubmit,
    onCancel,
    onClose,
  } = useDocumentDialog(initial, showsNotes, onSubmit, onClosed);

  // aria-disabled rather than disabled, so that the focused button keeps the focus while the request is sent.
  const busyState = isBusy ? 'true' : undefined;

  return createPortal(
    <dialog
      ref={dialog}
      className="dialog"
      aria-labelledby={ids.heading}
      onCancel={(event) => {
        // Escape must not drop a request that is being sent.
        if (isBusy) event.preventDefault();
      }}
      onClose={onClose}
    >
      <form
        className="dialog-body"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          onFormSubmit();
        }}
      >
        <h2 id={ids.heading} className="dialog-title">
          {heading}
        </h2>
        <div className="field">
          <label htmlFor={ids.title}>{t('Title')}</label>
          <input
            ref={titleInput}
            id={ids.title}
            name="title"
            className="input"
            required
            maxLength={TEXT_MAXIMUM_LENGTH}
            autoComplete="off"
            value={form.title}
            onChange={(event) => onTitleChange(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={ids.author}>
            {t('Author')} <span className="optional">{t('(optional)')}</span>
          </label>
          <input
            id={ids.author}
            name="author"
            className="input"
            maxLength={TEXT_MAXIMUM_LENGTH}
            autoComplete="off"
            value={form.author}
            onChange={(event) => onAuthorChange(event.target.value)}
          />
        </div>
        <fieldset className="field">
          <legend>{t('Kind')}</legend>
          <div className="segmented">
            {documentKindChoices(t).map(({ kind, label }) => (
              <label key={kind} className="segmented-option">
                <input
                  type="radio"
                  name="kind"
                  value={kind}
                  checked={form.kind === kind}
                  onChange={() => onKindChange(kind)}
                />
                <span>{label}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <label className="checkbox">
          <input
            type="checkbox"
            name="unwarp"
            aria-describedby={ids.unwarpHint}
            checked={form.unwarp}
            onChange={(event) => onUnwarpChange(event.target.checked)}
          />
          <span>
            <span className="checkbox-label">{t('Flatten curved pages')}</span>
            <span id={ids.unwarpHint} className="hint">
              {t('For pages curved near the binding; done by the PC, a little slower.')}
            </span>
          </span>
        </label>
        {form.notes !== null && (
          <div className="field">
            <label htmlFor={ids.notes}>
              {t('Notes')} <span className="optional">{t('(optional)')}</span>
            </label>
            <textarea
              id={ids.notes}
              name="notes"
              className="input"
              rows={NOTES_ROWS}
              maxLength={NOTES_MAXIMUM_LENGTH}
              value={form.notes}
              onChange={(event) => onNotesChange(event.target.value)}
            />
          </div>
        )}
        <p className="form-error" role="alert" hidden={error === null}>
          {error ?? ''}
        </p>
        <div className="dialog-actions">
          <button type="button" className="btn" aria-disabled={busyState} onClick={onCancel}>
            {t('Cancel')}
          </button>
          <button type="submit" className="btn btn-primary" aria-disabled={busyState}>
            {submitLabel}
          </button>
        </div>
      </form>
    </dialog>,
    document.body,
  );
};
