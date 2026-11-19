import type { FC } from 'react';
import { useTranslation } from 'react-i18next';

import { isBeingRead, type PageDetails } from '../../../domain/page-details.ts';
import type { FormulaTypesetter } from '../sanitized-html/use-sanitized-html.ts';
import { Icon } from '../shell/icon.tsx';
import { usePageText } from './use-page-text.ts';

export interface TextPaneProps {
  readonly page: PageDetails;
  readonly sanitizedHtml: string;
  readonly typesetFormulas: FormulaTypesetter;
  readonly showsMarkdown: boolean;
  readonly onToggleMarkdown: () => void;
  readonly onCopyMarkdown: (markdown: string) => void;
}

export const TextPane: FC<TextPaneProps> = ({
  page,
  sanitizedHtml,
  typesetFormulas,
  showsMarkdown,
  onToggleMarkdown,
  onCopyMarkdown,
}) => {
  const { t } = useTranslation();
  const hasMarkdown = page.markdown.trim() !== '';

  return (
    <section className="pane text-pane" aria-labelledby="text-title">
      <div className="pane-header">
        <h2 id="text-title" className="pane-title">
          {t('Recognized text')}
        </h2>
        <div className="pane-tools">
          <button type="button" className="btn btn-small" aria-pressed={showsMarkdown} onClick={onToggleMarkdown}>
            {t('Raw Markdown')}
          </button>
          <button
            type="button"
            className="btn btn-small btn-ghost"
            aria-disabled={hasMarkdown ? undefined : 'true'}
            onClick={() => {
              if (hasMarkdown) onCopyMarkdown(page.markdown);
            }}
          >
            <Icon name="copy" />
            {t('Copy')}
          </button>
        </div>
      </div>
      <div className="text-body">
        <PageText
          page={page}
          sanitizedHtml={sanitizedHtml}
          showsMarkdown={showsMarkdown}
          typesetFormulas={typesetFormulas}
        />
      </div>
    </section>
  );
};

interface PageTextProps {
  readonly page: PageDetails;
  readonly sanitizedHtml: string;
  readonly showsMarkdown: boolean;
  readonly typesetFormulas: FormulaTypesetter;
}

const PageText: FC<PageTextProps> = ({ page, sanitizedHtml, showsMarkdown, typesetFormulas }) => {
  const { t } = useTranslation();
  const hasMarkdown = page.markdown.trim() !== '';
  if (isBeingRead(page.status)) {
    return (
      <div className="state state-loading" role="status">
        <span className="spinner" aria-hidden="true" />
        <span>{page.status === 'queued' ? t('Waiting to be read…') : t('Reading…')}</span>
      </div>
    );
  }
  if (page.status === 'error' && !hasMarkdown) {
    return <p className="state">{t('No text: this page couldn’t be read.')}</p>;
  }
  if (showsMarkdown) {
    return hasMarkdown ? (
      <pre className="markdown-source">{page.markdown}</pre>
    ) : (
      <p className="state">{t('Empty Markdown.')}</p>
    );
  }
  if (sanitizedHtml.trim() === '') return <p className="state">{t('No text recognized on this page.')}</p>;
  return (
    <RecognizedText
      sanitizedHtml={sanitizedHtml}
      version={page.reading?.readAt ?? ''}
      typesetFormulas={typesetFormulas}
    />
  );
};

interface RecognizedTextProps {
  readonly sanitizedHtml: string;
  // Changes with each reading of the text, which rewrites the illustrations in place under the same addresses.
  readonly version: string;
  readonly typesetFormulas: FormulaTypesetter;
}

const RecognizedText: FC<RecognizedTextProps> = ({ sanitizedHtml, version, typesetFormulas }) => {
  const container = usePageText(sanitizedHtml, version, typesetFormulas);
  return <div ref={container} className="ocr-render" />;
};
