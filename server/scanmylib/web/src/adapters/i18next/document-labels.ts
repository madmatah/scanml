import type { TFunction } from 'i18next';

import { DOCUMENT_KINDS, type DocumentKind, isDocumentKind } from '../../domain/document-summary.ts';

export interface DocumentKindChoice {
  readonly kind: DocumentKind;
  readonly label: string;
}

function knownKindLabel(t: TFunction, kind: DocumentKind): string {
  switch (kind) {
    case 'book':
      return t('Book');
    case 'document':
      return t('Other');
  }
}

export function documentKindLabel(t: TFunction, kind: string): string {
  return isDocumentKind(kind) ? knownKindLabel(t, kind) : kind;
}

export function documentKindChoices(t: TFunction): DocumentKindChoice[] {
  return DOCUMENT_KINDS.map((kind) => ({ kind, label: knownKindLabel(t, kind) }));
}
