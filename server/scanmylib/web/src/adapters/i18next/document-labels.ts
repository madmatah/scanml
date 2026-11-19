import type { TFunction } from 'i18next';

import { DOCUMENT_KINDS, type DocumentKind, isDocumentKind } from '../../domain/document-summary.ts';

export interface DocumentKindChoice {
  readonly kind: DocumentKind;
  readonly label: string;
}

const knownKindLabel = (t: TFunction, kind: DocumentKind): string => {
  switch (kind) {
    case 'book':
      return t('Book');
    case 'document':
      return t('Other');
  }
};

export const documentKindLabel = (t: TFunction, kind: string): string => {
  return isDocumentKind(kind) ? knownKindLabel(t, kind) : kind;
};

export const documentKindChoices = (t: TFunction): DocumentKindChoice[] => {
  return DOCUMENT_KINDS.map((kind) => ({ kind, label: knownKindLabel(t, kind) }));
};
