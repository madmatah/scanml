import { type RefObject, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { DocumentFields } from '../../../application/document-catalog.ts';
import type { DocumentKind } from '../../../domain/document-summary.ts';
import { errorMessage } from '../shell/error-message.ts';
import {
  type DocumentForm,
  type EditedDocument,
  editedDocumentForm,
  newDocumentForm,
  submittedForm,
  withKind,
  withUnwarp,
} from './document-form.ts';
import { useModal } from './use-modal.ts';

export interface DocumentDialogState {
  readonly dialog: RefObject<HTMLDialogElement | null>;
  readonly titleInput: RefObject<HTMLInputElement | null>;
  readonly form: DocumentForm;
  readonly error: string | null;
  readonly isBusy: boolean;
  readonly onTitleChange: (title: string) => void;
  readonly onAuthorChange: (author: string) => void;
  readonly onKindChange: (kind: DocumentKind) => void;
  readonly onUnwarpChange: (unwarp: boolean) => void;
  readonly onNotesChange: (notes: string) => void;
  readonly onFormSubmit: () => void;
  readonly onCancel: () => void;
  readonly onClose: () => void;
}

export const useDocumentDialog = <Saved>(
  initial: EditedDocument | undefined,
  showsNotes: boolean,
  onSubmit: (fields: DocumentFields) => Promise<Saved>,
  onClosed: (saved: Saved | null) => void,
): DocumentDialogState => {
  const { t } = useTranslation();
  const dialog = useRef<HTMLDialogElement>(null);
  const titleInput = useRef<HTMLInputElement>(null);
  const saved = useRef<{ readonly answer: Saved } | null>(null);
  const [form, setForm] = useState<DocumentForm>(() =>
    initial === undefined ? newDocumentForm(showsNotes) : editedDocumentForm(initial, showsNotes),
  );
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setBusy] = useState(false);
  const returnFocus = useModal(dialog, titleInput);

  const save = async (fields: DocumentFields): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      saved.current = { answer: await onSubmit(fields) };
      dialog.current?.close();
    } catch (failure) {
      setError(errorMessage(t, failure, t('Could not save.')));
    } finally {
      setBusy(false);
    }
  };

  const submit = (): void => {
    if (isBusy) return;
    const submitted = submittedForm(form);
    if ('missing' in submitted) {
      setError(t('The title is required.'));
      titleInput.current?.focus();
      return;
    }
    // save shows its own failures in the dialog, so its promise never rejects.
    void save(submitted.fields);
  };

  return {
    dialog,
    titleInput,
    form,
    error,
    isBusy,
    onTitleChange: (title) => {
      setForm({ ...form, title });
      setError(null);
    },
    onAuthorChange: (author) => setForm({ ...form, author }),
    onKindChange: (kind) => setForm(withKind(form, kind)),
    onUnwarpChange: (unwarp) => setForm(withUnwarp(form, unwarp)),
    onNotesChange: (notes) => setForm({ ...form, notes }),
    onFormSubmit: submit,
    onCancel: () => {
      if (!isBusy) dialog.current?.close();
    },
    onClose: () => {
      returnFocus();
      onClosed(saved.current === null ? null : saved.current.answer);
    },
  };
};
