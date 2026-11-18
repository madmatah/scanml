import type { PageDetails } from '../../src/domain/page-details.ts';

export const SAMPLE_PAGE_ID = 'de215798-031a-4b20-a867-49c12e3baabe';
export const SAMPLE_DOCUMENT_ID = '95bbeb79-4351-432f-a53c-d3658892ff50';

export function samplePageDetails(changes: Partial<PageDetails> = {}): PageDetails {
  return {
    id: SAMPLE_PAGE_ID,
    documentId: SAMPLE_DOCUMENT_ID,
    key: 'p0011',
    sessionId: '6b1f0c3e-63c1-4a3f-9d43-0f1b0c9a1b2c',
    sequence: 3,
    capturedAt: '2026-11-14T15:31:00+00:00',
    uploadedAt: '2026-11-14T15:31:05+00:00',
    status: 'done',
    error: null,
    number: 11,
    numberEnd: null,
    pageLabel: '11',
    numberSource: 'detected',
    detectedNumbers: ['11'],
    hintNumber: null,
    manualNumber: null,
    isExcluded: false,
    duplicateOf: null,
    placement: 'number',
    rotation: 0,
    width: 800,
    height: 1011,
    reading: {
      engine: 'example-engine',
      durationSeconds: 2.3,
      readAt: '2026-11-14T15:32:00+00:00',
      illustrationCount: 2,
      characterCount: 1234,
    },
    imageUrl: `/api/pages/${SAMPLE_PAGE_ID}/image`,
    markdown: 'Example text.',
    ...changes,
  };
}
