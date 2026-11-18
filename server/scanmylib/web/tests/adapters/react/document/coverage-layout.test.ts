import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import {
  type AxisLabel,
  axisLabels,
  type CoverageSegment,
  coverageSegments,
  scannedPageCount,
} from '../../../../src/adapters/react/document/coverage-layout.ts';
import type { PageRange } from '../../../../src/domain/document-summary.ts';

const RANGES: PageRange[] = [
  [11, 15],
  [18, 21],
];
const GAPS: PageRange[] = [[16, 17]];

describe('The coverage layout', () => {
  describe('The scannedPageCount() function', () => {
    describe('When the scans cover two ranges', () => {
      let count: number;
      beforeEach(() => {
        count = scannedPageCount(RANGES);
      });

      it('should count the pages of both, their bounds included', () => {
        assert.equal(count, 9);
      });
    });
  });

  describe('The coverageSegments() function', () => {
    describe('When a gap lies between two scanned ranges', () => {
      let segments: CoverageSegment[];
      beforeEach(() => {
        segments = coverageSegments(RANGES, GAPS);
      });

      it('should lay the ranges and the gap out in the order of their pages', () => {
        assert.deepEqual(segments, [
          { range: [11, 15], isMissing: false },
          { range: [16, 17], isMissing: true },
          { range: [18, 21], isMissing: false },
        ]);
      });
    });
  });

  describe('The axisLabels() function', () => {
    describe('When the segments are far enough apart', () => {
      let labels: AxisLabel[];
      beforeEach(() => {
        labels = axisLabels(coverageSegments(RANGES, GAPS), 11, 21);
      });

      it('should number the start of each segment, and the last page at the right end', () => {
        assert.deepEqual(labels, [
          { pageNumber: 11, positionRatio: 0, isLast: false },
          { pageNumber: 16, positionRatio: 5 / 11, isLast: false },
          { pageNumber: 18, positionRatio: 7 / 11, isLast: false },
          { pageNumber: 21, positionRatio: 1, isLast: true },
        ]);
      });
    });

    describe('When a segment starts too close to the one before', () => {
      let labels: AxisLabel[];
      beforeEach(() => {
        const ranges: PageRange[] = [
          [1, 50],
          [52, 100],
        ];
        labels = axisLabels(coverageSegments(ranges, [[51, 51]]), 1, 100);
      });

      it('should leave its number out, so that no two numbers overlap', () => {
        assert.deepEqual(
          labels.map((label) => label.pageNumber),
          [1, 51, 100],
        );
      });
    });

    describe('When the last segment starts too close to the right end', () => {
      let labels: AxisLabel[];
      beforeEach(() => {
        const ranges: PageRange[] = [
          [1, 97],
          [99, 100],
        ];
        labels = axisLabels(coverageSegments(ranges, [[98, 98]]), 1, 100);
      });

      it('should keep the last page number at the right end in its place', () => {
        assert.deepEqual(
          labels.map((label) => label.pageNumber),
          [1, 100],
        );
      });
    });

    describe('When a single page is scanned', () => {
      let labels: AxisLabel[];
      beforeEach(() => {
        labels = axisLabels(coverageSegments([[7, 7]], []), 7, 7);
      });

      it('should number it once, at the start', () => {
        assert.deepEqual(labels, [{ pageNumber: 7, positionRatio: 0, isLast: false }]);
      });
    });
  });
});
