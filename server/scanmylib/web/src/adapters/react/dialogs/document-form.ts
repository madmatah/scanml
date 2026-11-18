import type { DocumentFields } from '../../../application/document-catalog.ts';
import {
  type DocumentKind,
  isDocumentKind,
  NEW_DOCUMENT_KIND,
  unwarpsByDefault,
} from '../../../domain/document-summary.ts';

export interface DocumentForm {
  readonly title: string;
  readonly author: string;
  readonly kind: DocumentKind;
  readonly unwarp: boolean;
  readonly isUnwarpChosen: boolean;
  readonly notes: string | null;
}

export interface EditedDocument {
  readonly title: string;
  readonly author: string;
  readonly kind: string;
  readonly unwarp: boolean;
  readonly notes: string;
}

export type SubmittedForm = { readonly fields: DocumentFields } | { readonly missing: 'title' };

export function newDocumentForm(showsNotes = false): DocumentForm {
  return {
    title: '',
    author: '',
    kind: NEW_DOCUMENT_KIND,
    unwarp: unwarpsByDefault(NEW_DOCUMENT_KIND),
    isUnwarpChosen: false,
    notes: showsNotes ? '' : null,
  };
}

export function editedDocumentForm(document: EditedDocument, showsNotes: boolean): DocumentForm {
  return {
    title: document.title,
    author: document.author,
    kind: isDocumentKind(document.kind) ? document.kind : NEW_DOCUMENT_KIND,
    unwarp: document.unwarp,
    isUnwarpChosen: true,
    notes: showsNotes ? document.notes : null,
  };
}

export function withKind(form: DocumentForm, kind: DocumentKind): DocumentForm {
  return { ...form, kind, unwarp: form.isUnwarpChosen ? form.unwarp : unwarpsByDefault(kind) };
}

export function withUnwarp(form: DocumentForm, unwarp: boolean): DocumentForm {
  return { ...form, unwarp, isUnwarpChosen: true };
}

export function submittedForm(form: DocumentForm): SubmittedForm {
  const title = form.title.trim();
  if (title === '') return { missing: 'title' };
  const fields: DocumentFields = { title, author: form.author.trim(), kind: form.kind, unwarp: form.unwarp };
  return { fields: form.notes === null ? fields : { ...fields, notes: form.notes.trim() } };
}
