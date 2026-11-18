import type { DocumentDetails, DocumentWithPages } from '../domain/document-details.ts';
import type { DocumentFields } from './document-catalog.ts';

export interface DocumentStore {
  readDocument(documentId: string, signal: AbortSignal): Promise<DocumentWithPages>;
  readDocumentHtml(documentId: string, signal: AbortSignal): Promise<string>;
  updateDocument(documentId: string, fields: DocumentFields): Promise<DocumentDetails>;
  deleteDocument(documentId: string): Promise<void>;
  reorderPages(documentId: string, pageIds: readonly string[]): Promise<DocumentWithPages>;
  resetPageOrder(documentId: string): Promise<DocumentWithPages>;
  markdownUrl(documentId: string): string;
  archiveUrl(documentId: string, includesScans: boolean): string;
}
