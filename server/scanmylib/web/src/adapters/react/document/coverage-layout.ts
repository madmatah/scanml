import type { PageRange } from '../../../domain/document-summary.ts';

export interface CoverageSegment {
  readonly range: PageRange;
  readonly isMissing: boolean;
}

export interface AxisLabel {
  readonly pageNumber: number;
  readonly positionRatio: number;
  readonly isLast: boolean;
}

// Below this distance, as a share of the bar's width, two numbers of the axis would overlap.
export const LEAST_LABEL_SPACING_RATIO = 0.09;

export const pageCount = ([start, end]: PageRange): number => {
  return end - start + 1;
};

export const scannedPageCount = (ranges: readonly PageRange[]): number => {
  return ranges.reduce((total, range) => total + pageCount(range), 0);
};

export const coverageSegments = (ranges: readonly PageRange[], gaps: readonly PageRange[]): CoverageSegment[] => {
  return [
    ...ranges.map((range) => ({ range, isMissing: false })),
    ...gaps.map((range) => ({ range, isMissing: true })),
  ].sort((first, second) => first.range[0] - second.range[0]);
};

export const axisLabels = (
  segments: readonly CoverageSegment[],
  lowestNumber: number,
  highestNumber: number,
): AxisLabel[] => {
  if (lowestNumber === highestNumber) return [{ pageNumber: lowestNumber, positionRatio: 0, isLast: false }];
  const span = pageCount([lowestNumber, highestNumber]);
  const labels: AxisLabel[] = [];
  for (const { range } of segments) {
    const positionRatio = (range[0] - lowestNumber) / span;
    const previous = labels.at(-1);
    if (previous === undefined || positionRatio - previous.positionRatio >= LEAST_LABEL_SPACING_RATIO) {
      labels.push({ pageNumber: range[0], positionRatio, isLast: false });
    }
  }
  while (labels.length > 1 && 1 - (labels.at(-1)?.positionRatio ?? 0) < LEAST_LABEL_SPACING_RATIO) labels.pop();
  return [...labels, { pageNumber: highestNumber, positionRatio: 1, isLast: true }];
};
