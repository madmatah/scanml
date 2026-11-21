import type { FC } from 'react';

import type { DocumentSummary } from '../../../domain/document-summary.ts';
import { Icon } from '../shell/icon.tsx';
import { versionedUrl } from '../shell/versioned-url.ts';

export interface DocumentCoverProps {
  readonly document: DocumentSummary;
  readonly className: string;
}

export const DocumentCover: FC<DocumentCoverProps> = ({ document, className }) => {
  const { coverThumbnailUrl } = document;
  return (
    <div className={className}>
      {coverThumbnailUrl === null ? (
        <span className="doc-cover-placeholder" aria-hidden="true">
          <Icon name="book" />
        </span>
      ) : (
        // The cover may change or be rotated: its thumbnail follows the document's version.
        <img src={versionedUrl(coverThumbnailUrl, document.updatedAt)} alt="" loading="lazy" decoding="async" />
      )}
    </div>
  );
};
