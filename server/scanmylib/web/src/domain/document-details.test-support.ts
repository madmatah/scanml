import type { PageSummary } from './document-details.ts';

export function samplePage(id: string, changes: Partial<PageSummary> = {}): PageSummary {
  return {
    id,
    key: `k-${id}`,
    status: 'done',
    pageLabel: '11',
    numberEnd: null,
    numberSource: 'detected',
    isExcluded: false,
    duplicateOf: null,
    isInDocument: true,
    placement: 'number',
    position: null,
    rotation: 0,
    thumbnailUrl: `/api/pages/${id}/thumb`,
    readAt: null,
    ...changes,
  };
}
