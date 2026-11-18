import type { PageSummary } from '../../src/domain/document-details.ts';

export function samplePage(id: string, changes: Partial<PageSummary> = {}): PageSummary {
  return {
    id,
    status: 'done',
    pageLabel: '11',
    numberSource: 'detected',
    isExcluded: false,
    duplicateOf: null,
    isInDocument: true,
    placement: 'number',
    rotation: 0,
    thumbnailUrl: `/api/pages/${id}/thumb`,
    ...changes,
  };
}
