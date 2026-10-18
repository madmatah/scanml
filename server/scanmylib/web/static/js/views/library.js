/** Library: the documents, newest activity first, and document creation. */
import { api, NetworkError, versionedUrl } from '../api.js';
import { documentDialog } from '../components/dialogs.js';
import { icon } from '../components/icons.js';
import { emptyState, errorState, loadingState } from '../components/states.js';
import { toast } from '../components/toast.js';
import { h, NodeCache, syncChildren } from '../lib/dom.js';
import { errorMessage, isAbort } from '../lib/errors.js';
import { formatRanges, formatRelative, quoted } from '../lib/format.js';
import { t, tNodes, tn } from '../lib/i18n.js';
import { documentKind } from '../lib/labels.js';
import { randomUuid } from '../lib/uuid.js';
import { href, navigate, paths } from '../router.js';

/** The search field appears from this many documents on. */
const SEARCH_THRESHOLD = 4;

/** Lower-case text without accents, for searching. */
function normalize(text) {
  return (text ?? '')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase();
}

function statusChips(doc) {
  const { stats } = doc;
  return [
    h('li', { class: 'chip' }, documentKind(doc.kind)),
    stats.processing > 0 && h('li', { class: 'chip chip-info' }, t('{count} in progress', { count: stats.processing })),
    stats.queued > 0 && h('li', { class: 'chip chip-warn' }, t('{count} queued', { count: stats.queued })),
    stats.error > 0 && h('li', { class: 'chip chip-danger' }, tn('{count} error', '{count} errors', stats.error)),
    stats.excluded > 0 && h('li', { class: 'chip' }, tn('{count} excluded', '{count} excluded', stats.excluded)),
    stats.duplicates > 0 && h('li', { class: 'chip' }, tn('{count} duplicate', '{count} duplicates', stats.duplicates)),
  ];
}

function coverageSummary(coverage) {
  if (!coverage || coverage.min === null || coverage.min === undefined) {
    return coverage?.unnumbered
      ? tn('{count} unnumbered page', '{count} unnumbered pages', coverage.unnumbered)
      : t('No numbered page');
  }
  const parts = [t('Pages {label}', { label: coverage.label || formatRanges(coverage.ranges ?? []) })];
  if (coverage.gaps?.length) parts.push(t('missing {ranges}', { ranges: formatRanges(coverage.gaps) }));
  return parts.join(' · ');
}

function documentCard(doc) {
  const { stats } = doc;
  // The cover page may change or be rotated: its thumbnail follows the document's version.
  const cover = doc.cover_thumb_url
    ? h('img', { src: versionedUrl(doc.cover_thumb_url, doc.updated_at), alt: '', loading: 'lazy', decoding: 'async' })
    : h('span', { class: 'doc-cover-placeholder', 'aria-hidden': 'true' }, icon('book'));
  const doneRatio = stats.pages ? stats.done / stats.pages : 0;

  return h(
    'li',
    { class: 'doc-card' },
    h(
      'a',
      { class: 'doc-card-link', href: href(paths.document(doc.id)) },
      h('div', { class: 'doc-cover' }, cover),
      h(
        'div',
        { class: 'doc-card-body' },
        h('h2', { class: 'doc-card-title' }, doc.title),
        doc.author && h('p', { class: 'doc-card-author' }, doc.author),
        h(
          'p',
          { class: 'doc-card-progress' },
          h(
            'span',
            { class: 'meter', 'aria-hidden': 'true' },
            h('span', { class: 'meter-fill', style: { width: `${Math.round(doneRatio * 100)}%` } }),
          ),
          h('span', {}, `${stats.done} / ${tn('{count} page processed', '{count} pages processed', stats.pages)}`),
        ),
        h('p', { class: 'doc-card-coverage' }, coverageSummary(doc.coverage)),
        h('ul', { class: 'chips', role: 'list' }, statusChips(doc)),
        h('p', { class: 'doc-card-updated' }, t('Updated {time}', { time: formatRelative(doc.updated_at) })),
      ),
    ),
  );
}

/** Data shown by a card: it is re-rendered only when this changes. */
function cardSignature(doc) {
  return JSON.stringify([
    doc.title,
    doc.author,
    doc.kind,
    doc.stats,
    doc.coverage,
    doc.cover_thumb_url,
    formatRelative(doc.updated_at),
  ]);
}

export function mountLibrary(root, { signal, monitor, setTitle }) {
  setTitle(t('Library'));
  let documents = null;
  let query = '';
  let lastQueueKey = null;
  const cards = new NodeCache();

  const summary = h('p', { class: 'view-subtitle' });
  const search = h('input', {
    type: 'search',
    class: 'input',
    placeholder: t('Search for a title, an author…'),
    'aria-label': t('Search the library'),
    autocomplete: 'off',
  });
  const searchField = h('div', { class: 'search-field', hidden: true }, icon('search'), search);
  const newButton = h('button', { type: 'button', class: 'btn btn-primary' }, icon('plus'), t('New document'));
  const list = h('ul', { class: 'doc-grid', role: 'list' });
  const content = h('div', { class: 'library-content' }, loadingState());
  const footer = h('p', { class: 'library-footer', hidden: true });

  root.replaceChildren(
    h(
      'section',
      { class: 'view library' },
      h(
        'header',
        { class: 'view-header' },
        h('div', { class: 'view-heading' }, h('h1', { tabindex: '-1' }, t('Library')), summary),
        h('div', { class: 'view-actions' }, searchField, newButton),
      ),
      content,
      footer,
    ),
  );

  function renderFooter() {
    const directory = monitor.status?.library_dir;
    footer.hidden = !directory;
    if (directory) {
      footer.replaceChildren(
        ...tNodes('Markdown files and illustrations are stored in {folder}', {
          folder: h('code', { class: 'path' }, directory),
        }),
      );
    }
  }

  function render() {
    renderFooter();
    if (!documents) return;
    const totalPages = documents.reduce((total, doc) => total + doc.stats.pages, 0);
    const documentCount = tn('{count} document', '{count} documents', documents.length);
    summary.textContent = documents.length
      ? `${documentCount} · ${tn('{count} page', '{count} pages', totalPages)}`
      : '';
    searchField.hidden = documents.length < SEARCH_THRESHOLD;
    if (searchField.hidden) {
      query = '';
      search.value = '';
    }

    if (!documents.length) {
      content.replaceChildren(
        emptyState({
          iconName: 'book',
          title: t('Your library is empty'),
          message: t(
            'Create a document, then add photos to it from this browser, ' + 'or scan directly with the Android app.',
          ),
          actions: [
            h(
              'button',
              { type: 'button', class: 'btn btn-primary', onClick: createDocument },
              icon('plus'),
              t('New document'),
            ),
            h('a', { class: 'btn', href: href(paths.pairing()) }, icon('phone'), t('Pair the phone')),
          ],
        }),
      );
      return;
    }

    const needle = normalize(query.trim());
    const visible = needle
      ? documents.filter((doc) => normalize(`${doc.title} ${doc.author ?? ''}`).includes(needle))
      : documents;
    syncChildren(
      list,
      visible.map((doc) => cards.get(doc.id, cardSignature(doc), () => documentCard(doc))),
    );
    cards.prune();
    if (visible.length) {
      if (list.parentNode !== content) content.replaceChildren(list);
    } else {
      const message = t('No document matches {query}.', { query: quoted(query.trim()) });
      content.replaceChildren(h('p', { class: 'state' }, message));
    }
  }

  async function load() {
    try {
      documents = await api.listDocuments({ signal });
      render();
    } catch (error) {
      if (isAbort(error)) return;
      if (documents) {
        // While the server is unreachable the banner says so; keep the last list.
        if (!(error instanceof NetworkError)) {
          toast(errorMessage(error, t('Could not refresh the library.')), { tone: 'error' });
        }
      } else {
        content.replaceChildren(errorState({ message: errorMessage(error), onRetry: load }));
      }
    }
  }

  async function createDocument() {
    const id = randomUuid(); // one id per dialog, so a retried request stays idempotent
    const created = await documentDialog({
      heading: t('New document'),
      submitLabel: t('Create document'),
      onSubmit: (values) => api.createDocument(id, values),
    });
    if (!created) return;
    toast(t('Document {title} created.', { title: quoted(created.title) }), { tone: 'success' });
    navigate(paths.document(created.id));
  }

  /** Reloads when the OCR queue moves (new uploads from the phone, pages done…). */
  function onStatusChange() {
    renderFooter();
    const queue = monitor.status?.queue;
    if (!queue) return;
    const key = [queue.queued, queue.processing, queue.done, queue.error].join('/');
    if (lastQueueKey !== null && key !== lastQueueKey) load();
    lastQueueKey = key;
  }

  function onVisibilityChange() {
    if (!document.hidden) load();
  }

  search.addEventListener('input', () => {
    query = search.value;
    render();
  });
  newButton.addEventListener('click', createDocument);
  monitor.addEventListener('change', onStatusChange);
  document.addEventListener('visibilitychange', onVisibilityChange);
  // Keeps "Updated 5 minutes ago" current while the screen stays open.
  const relativeDatesTimer = setInterval(render, 60_000);
  load();

  return () => {
    monitor.removeEventListener('change', onStatusChange);
    document.removeEventListener('visibilitychange', onVisibilityChange);
    clearInterval(relativeDatesTimer);
  };
}
