import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Clipboard } from '../../../application/clipboard.ts';
import { isBeingRead, type PageDetails } from '../../../domain/page-details.ts';
import { localizeMarkers } from '../sanitized-html/page-markers.ts';
import { type FormulaTypesetter, useSanitizedHtml } from '../sanitized-html/use-sanitized-html.ts';
import { Icon } from '../shell/icon.tsx';
import type { Toasts } from '../shell/toasts.ts';
import { versionedUrl } from '../shell/versioned-url.ts';

export interface TextPaneProps {
  readonly page: PageDetails;
  readonly sanitizedHtml: string;
  readonly typesetFormulas: FormulaTypesetter;
  readonly clipboard: Clipboard;
  readonly toasts: Toasts;
}

export function TextPane({ page, sanitizedHtml, typesetFormulas, clipboard, toasts }: TextPaneProps) {
  const { t } = useTranslation();
  const [showsMarkdown, setShowsMarkdown] = useState(false);
  const hasMarkdown = page.markdown.trim() !== '';

  async function copyMarkdown(): Promise<void> {
    if (await clipboard.copyText(page.markdown)) toasts.show(t('Markdown copied.'), 'success');
    else toasts.show(t('Could not copy.'), 'error');
  }

  return (
    <section className="pane text-pane" aria-labelledby="text-title">
      <div className="pane-header">
        <h2 id="text-title" className="pane-title">
          {t('Recognized text')}
        </h2>
        <div className="pane-tools">
          <button
            type="button"
            className="btn btn-small"
            aria-pressed={showsMarkdown}
            onClick={() => setShowsMarkdown(!showsMarkdown)}
          >
            {t('Raw Markdown')}
          </button>
          <button
            type="button"
            className="btn btn-small btn-ghost"
            aria-disabled={hasMarkdown ? undefined : 'true'}
            onClick={() => {
              // copyMarkdown tells its outcome in a toast, and the clipboard's copy never rejects.
              if (hasMarkdown) void copyMarkdown();
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
}

interface PageTextProps {
  readonly page: PageDetails;
  readonly sanitizedHtml: string;
  readonly showsMarkdown: boolean;
  readonly typesetFormulas: FormulaTypesetter;
}

function PageText({ page, sanitizedHtml, showsMarkdown, typesetFormulas }: PageTextProps) {
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
}

interface RecognizedTextProps {
  readonly sanitizedHtml: string;
  // Changes with each reading of the text, which rewrites the illustrations in place under the same addresses.
  readonly version: string;
  readonly typesetFormulas: FormulaTypesetter;
}

function RecognizedText({ sanitizedHtml, version, typesetFormulas }: RecognizedTextProps) {
  const { t } = useTranslation();
  // The api writes its markers in English; the illustrations get the version of the reading before any of them loads.
  const prepare = useCallback(
    (content: DocumentFragment) => {
      localizeMarkers(t, content);
      for (const illustration of content.querySelectorAll('img[src]')) {
        const address = illustration.getAttribute('src');
        if (address !== null) illustration.setAttribute('src', versionedUrl(address, version));
      }
    },
    [t, version],
  );
  const container = useSanitizedHtml(sanitizedHtml, prepare, typesetFormulas);
  return <div ref={container} className="ocr-render" />;
}
