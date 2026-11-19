import type { PageSummary } from './document-details.ts';

export interface PageReading {
  readonly engine: string | null;
  readonly durationSeconds: number | null;
  readonly readAt: string | null;
  readonly illustrationCount: number | null;
  readonly characterCount: number | null;
}

export interface PageDetails {
  readonly id: string;
  readonly documentId: string;
  readonly key: string;
  readonly sessionId: string | null;
  readonly sequence: number | null;
  readonly capturedAt: string;
  readonly uploadedAt: string;
  readonly status: string;
  readonly error: string | null;
  readonly number: number | null;
  readonly numberEnd: number | null;
  readonly pageLabel: string | null;
  readonly numberSource: string | null;
  readonly detectedNumbers: readonly string[];
  readonly hintNumber: number | null;
  readonly manualNumber: number | null;
  readonly isExcluded: boolean;
  readonly duplicateOf: string | null;
  readonly placement: string | null;
  readonly rotation: number;
  readonly width: number;
  readonly height: number;
  readonly reading: PageReading | null;
  readonly imageUrl: string;
  readonly markdown: string;
}

export interface PageNeighbors {
  readonly previous: PageSummary | null;
  readonly next: PageSummary | null;
  readonly position: { readonly index: number; readonly count: number } | null;
}

export type PageNumberEntry = { readonly isValid: true; readonly number: number } | { readonly isValid: false };

const QUARTER_TURN_DEGREES = 90;
const FULL_TURN_DEGREES = 360;
const LOWEST_PAGE_NUMBER = 1;
const HIGHEST_PAGE_NUMBER = 9999;

// The api reads the text of a page in the background: until it is done, the page changes on its own.
export const isBeingRead = (status: string): boolean => {
  return status === 'queued' || status === 'processing';
};

// The pages around this one in the document's order, which the api lists as its reading order.
export const pageNeighbors = (pages: readonly PageSummary[], pageId: string): PageNeighbors => {
  const index = pages.findIndex((page) => page.id === pageId);
  if (index < 0) return { previous: null, next: null, position: null };
  return {
    previous: pages[index - 1] ?? null,
    next: pages[index + 1] ?? null,
    position: { index, count: pages.length },
  };
};

// A number field takes digits only, so a roman number of the front matter is not shown in it.
export const typedNumberOf = (page: PageDetails): number | null => {
  const arabicNumber = /^\d/.test(page.pageLabel ?? '') ? page.number : null;
  return page.manualNumber ?? arabicNumber;
};

export const readPageNumberEntry = (text: string): PageNumberEntry => {
  const number = Number(text);
  if (text.trim() === '' || !Number.isInteger(number) || number < LOWEST_PAGE_NUMBER || number > HIGHEST_PAGE_NUMBER) {
    return { isValid: false };
  }
  return { isValid: true, number };
};

export const turnedLeft = (rotation: number): number => {
  return (rotation + FULL_TURN_DEGREES - QUARTER_TURN_DEGREES) % FULL_TURN_DEGREES;
};

export const turnedRight = (rotation: number): number => {
  return (rotation + QUARTER_TURN_DEGREES) % FULL_TURN_DEGREES;
};
