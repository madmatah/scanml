import type { FC } from 'react';

import type { PageCoverage } from '../../../domain/document-summary.ts';
import { coverageSegments, pageCount } from '../document/coverage-layout.ts';

export interface CoverageBarProps {
  readonly coverage: PageCoverage;
}

// Drawn for the eye: the summary beside it says the same in words.
export const CoverageBar: FC<CoverageBarProps> = ({ coverage }) => {
  return (
    <span className="library-coverage-bar" aria-hidden="true">
      {coverageSegments(coverage.ranges, coverage.gaps).map(({ range, isMissing }) => (
        <span
          key={range[0]}
          className={isMissing ? 'coverage-segment is-missing' : 'coverage-segment is-scanned'}
          style={{ flexGrow: String(pageCount(range)) }}
        />
      ))}
    </span>
  );
};
