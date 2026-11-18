import type { DocumentDetails, DocumentWithPages } from '../domain/document-details.ts';
import type { DocumentFields } from './document-catalog.ts';

export interface DocumentStore {
  readDocument(documentId: string, signal: AbortSignal): Promise<DocumentWithPages>;
  updateDocument(documentId: string, fields: DocumentFields): Promise<DocumentDetails>;
  deleteDocument(documentId: string): Promise<void>;
  // Both answer the document with its pages in their new order.
  reorderPages(documentId: string, pageIds: readonly string[]): Promise<DocumentWithPages>;
  resetPageOrder(documentId: string): Promise<DocumentWithPages>;
  markdownUrl(documentId: string): string;
  archiveUrl(documentId: string, withScans: boolean): string;
}
