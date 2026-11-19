import type { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import {
  groupPages,
  hasPagesPlacedByHand,
  hasPlacedPages,
  type PageSummary,
} from '../../../domain/document-details.ts';
import { numberSourceLabel, pageShortLabel, pageStatusLabel } from '../../i18next/page-labels.ts';
import { pagePath } from '../shell/navigation.ts';
import { versionedUrl } from '../shell/versioned-url.ts';
import { pageGroupHeading } from './document-text.ts';
import { PlacementChip } from './placement-chip.tsx';

export interface PageGridProps {
  readonly pages: readonly PageSummary[];
}

export const PageGrid: FC<PageGridProps> = ({ pages }) => {
  const { t } = useTranslation();
  const groups = groupPages(pages);
  const situation = { hasPlacedPages: hasPlacedPages(groups), hasPagesPlacedByHand: hasPagesPlacedByHand(pages) };
  return (
    <div className="page-groups">
      {groups.map((group) => {
        const heading = pageGroupHeading(t, group.kind, situation);
        return (
          <section key={group.key} className="page-group">
            <div className="page-group-header">
              <h3 className="page-group-title">{`${heading.title} (${group.pages.length})`}</h3>
              <p className="page-group-hint">{heading.hint}</p>
            </div>
            {/* biome-ignore lint/a11y/noRedundantRoles: Safari drops the role of a list drawn without its markers. */}
            <ul className="page-grid" role="list">
              {group.pages.map((page) => (
                <PageCard key={page.id} page={page} showsUnplaced={situation.hasPlacedPages} />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
};

interface PageCardProps {
  readonly page: PageSummary;
  readonly showsUnplaced: boolean;
}

const PageCard: FC<PageCardProps> = ({ page, showsUnplaced }) => {
  const { t } = useTranslation();
  const status = pageStatusLabel(t, page.status);
  const source = numberSourceLabel(t, page.numberSource);
  const isDuplicate = page.duplicateOf !== null;
  const cardClasses = ['page-card', page.isExcluded && 'is-excluded', isDuplicate && 'is-duplicate'];
  return (
    <li className={cardClasses.filter(Boolean).join(' ')}>
      <Link className="page-card-link" to={pagePath(page.id)}>
        <span className="page-thumb">
          {/* The api draws the thumbnail of a rotated page again at the same address. */}
          <img src={versionedUrl(page.thumbnailUrl, String(page.rotation))} alt="" loading="lazy" decoding="async" />
          {page.status === 'processing' && (
            <span className="page-thumb-busy" aria-hidden="true">
              <span className="spinner" />
            </span>
          )}
        </span>
        <span className="page-card-body">
          <span className="page-card-label">{pageShortLabel(t, { page_label: page.pageLabel })}</span>
          {source !== null && (
            <span className={`chip chip-source source-${page.numberSource}`} title={source.description}>
              {source.label}
            </span>
          )}
          <PlacementChip page={page} showsUnplaced={showsUnplaced} />
          {page.status !== 'done' && <span className={`chip chip-${status.tone}`}>{status.label}</span>}
          {page.isExcluded && <span className="chip chip-outline">{t('Excluded', { context: 'one page' })}</span>}
          {isDuplicate && <span className="chip chip-warn">{t('Duplicate')}</span>}
        </span>
      </Link>
    </li>
  );
};
