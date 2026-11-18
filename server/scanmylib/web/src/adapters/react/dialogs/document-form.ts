import type { DocumentFields } from '../../../application/document-catalog.ts';
import type { DocumentKind } from '../../../domain/document-summary.ts';

export interface DocumentForm {
  readonly title: string;
  readonly author: string;
  readonly kind: DocumentKind;
  readonly unwarp: boolean;
  readonly isUnwarpChosen: boolean;
}

export type SubmittedForm = { readonly fields: DocumentFields } | { readonly missing: 'title' };

const NEW_DOCUMENT_KIND: DocumentKind = 'book';

// Books are photographed open, their pages curved near the binding; other documents lie flat.
function unwarpsByDefault(kind: DocumentKind): boolean {
  return kind === 'book';
}

export function newDocumentForm(): DocumentForm {
  return {
    title: '',
    author: '',
    kind: NEW_DOCUMENT_KIND,
    unwarp: unwarpsByDefault(NEW_DOCUMENT_KIND),
    isUnwarpChosen: false,
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
  return { fields: { title, author: form.author.trim(), kind: form.kind, unwarp: form.unwarp } };
}
