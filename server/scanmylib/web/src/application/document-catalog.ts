import type { DocumentSummary } from '../domain/document-summary.ts';

export interface DocumentFields {
  readonly title: string;
  readonly author: string;
  readonly kind: string;
  readonly unwarp: boolean;
  readonly notes?: string;
}

export interface DocumentCatalog {
  listDocuments(signal: AbortSignal): Promise<DocumentSummary[]>;
  createDocument(id: string, fields: DocumentFields): Promise<DocumentSummary>;
}
