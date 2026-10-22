/**
 * Document: metadata, coverage, exports, photo uploads from the browser and
 * the pages grid, with its "Organize" mode (components/page-organizer.js);
 * "Read document" opens the reading view (views/reader.js).
 * Refreshes itself while pages are waiting for OCR.
 */
import { api, links, versionedUrl } from '../api.js';
import { renderCoverage } from '../components/coverage.js';
import { confirmDialog, documentDialog } from '../components/dialogs.js';
import { icon } from '../components/icons.js';
import { createPageOrganizer, placementChip } from '../components/page-organizer.js';
import { emptyState, errorState, loadingState } from '../components/states.js';
import { toast } from '../components/toast.js';
import { copyText } from '../lib/clipboard.js';
import { h, NodeCache, setChildren, syncChildren, uniqueId } from '../lib/dom.js';
import { errorMessage, isAbort } from '../lib/errors.js';
import { formatBytes, formatPercent, quoted } from '../lib/format.js';
import { t, tc, tn } from '../lib/i18n.js';
import { documentKind, numberSource, pageShortLabel, pageStatus } from '../lib/labels.js';
import { randomUuid } from '../lib/uuid.js';
import { href, navigate, paths } from '../router.js';
import { uploads } from '../uploads.js';

const REFRESH_INTERVAL_MS = 3000;

/** Sections of the pages grid; the API lists pages in this order. */
const PAGE_GROUPS = {
  placed: () => ({ title: t('In the document'), hint: t('In the reading order of document.md.') }),
  unplaced: () => ({
    title: t('Unnumbered pages'),
    hint: t(
      'Nothing tells where they go: they are at the end of the document, in capture order. ' +
        '“Organize” can put them in their place.',
    ),
  }),
  pending: () => ({
    title: t('Not in the document yet'),
    hint: t('Waiting to be read, or couldn’t be read: they will join the document once their text is ready.'),
  }),
  excluded: () => ({ title: t('Excluded'), hint: t('Left out of document.md.') }),
  duplicate: () => ({ title: t('Duplicates'), hint: t('Replaced by a newer scan of the same page number.') }),
};

const STATS = [
  { key: 'pages', label: () => t('Pages') },
  { key: 'done', label: () => t('Text ready') },
  { key: 'queued', label: () => t('Queued'), tone: 'warn' },
  { key: 'processing', label: () => t('Being read'), tone: 'info' },
  { key: 'error', label: () => t('Couldn’t be read'), tone: 'danger' },
  { key: 'excluded', label: () => t('Excluded') },
  { key: 'duplicates', label: () => t('Duplicates') },
];

/** Mirrors the server's order: reading order (placed, then unplaced pages), then pending, excluded, duplicates. */
function groupOf(page) {
  if (page.in_document) return page.placement === 'unplaced' ? 'unplaced' : 'placed';
  if (page.excluded) return 'excluded';
  if (page.duplicate_of) return 'duplicate';
  return 'pending';
}

/** `withUnplaced`: show "to place" (only meaningful when other pages have a place). */
function pageCard(page, withUnplaced) {
  const status = pageStatus(page.status);
  const source = numberSource(page.number_source);
  return h(
    'li',
    { class: ['page-card', page.excluded && 'is-excluded', page.duplicate_of && 'is-duplicate'] },
    h(
      'a',
      { class: 'page-card-link', href: href(paths.page(page.id)) },
      h(
        'span',
        { class: 'page-thumb' },
        // The server re-renders the thumbnail of a rotated page under the same URL.
        h('img', {
          src: versionedUrl(page.thumb_url, page.rotation ?? 0),
          alt: '',
          loading: 'lazy',
          decoding: 'async',
        }),
        page.status === 'processing' &&
          h('span', { class: 'page-thumb-busy', 'aria-hidden': 'true' }, h('span', { class: 'spinner' })),
      ),
      h(
        'span',
        { class: 'page-card-body' },
        h('span', { class: 'page-card-label' }, pageShortLabel(page)),
        source &&
          h(
            'span',
            {
              class: ['chip', 'chip-source', `source-${page.number_source}`],
              title: source.description,
            },
            source.label,
          ),
        placementChip(page, withUnplaced),
        page.status !== 'done' && h('span', { class: ['chip', `chip-${status.tone}`] }, status.label),
        page.excluded && h('span', { class: 'chip chip-outline' }, tc('one page', 'Excluded')),
        page.duplicate_of && h('span', { class: 'chip chip-warn' }, t('Duplicate')),
      ),
    ),
  );
}

function pageSignature(page, withUnplaced) {
  return JSON.stringify([
    page.status,
    page.page_label,
    page.number_source,
    page.excluded,
    page.duplicate_of,
    page.thumb_url,
    page.rotation,
    page.placement,
    withUnplaced,
  ]);
}

/** Summary of the OCR queue: when it changes, pages were added or processed. */
function queueKey(status) {
  const queue = status?.queue;
  return queue ? [queue.queued, queue.processing, queue.done, queue.error].join('/') : null;
}

function statTiles(stats) {
  return STATS.map(({ key, label, tone }) => {
    const value = stats?.[key] ?? 0;
    return h(
      'div',
      { class: ['stat', value === 0 && 'is-zero', value > 0 && tone && `stat-${tone}`] },
      h('dt', { class: 'stat-label' }, label()),
      h('dd', { class: 'stat-value' }, String(value)),
    );
  });
}

/** Upload buttons and progress list for one document. */
function createUploader(documentId, { onUploaded }) {
  const filesInput = h('input', {
    type: 'file',
    accept: 'image/*',
    multiple: true,
    hidden: true,
    'data-upload': 'files',
  });
  const cameraInput = h('input', {
    type: 'file',
    accept: 'image/*',
    capture: 'environment',
    hidden: true,
    'data-upload': 'camera',
  });
  const pickButton = h('button', { type: 'button', class: 'btn btn-primary' }, icon('upload'), t('Import photos'));
  const cameraButton = h('button', { type: 'button', class: 'btn' }, icon('camera'), t('Take a photo'));

  const headline = h('p', { class: 'upload-headline' });
  const progress = h('progress', {
    class: 'upload-progress',
    max: 1,
    value: 0,
    'aria-label': t('Upload progress'),
  });
  const list = h('ul', { class: 'upload-list', role: 'list' });
  const retryButton = h(
    'button',
    { type: 'button', class: 'btn btn-small' },
    icon('refresh'),
    t('Retry failed uploads'),
  );
  const clearButton = h('button', { type: 'button', class: 'btn btn-small btn-ghost' }, t('Clear the list'));
  const panel = h(
    'div',
    { class: 'upload-panel', hidden: true },
    headline,
    progress,
    list,
    h('div', { class: 'upload-actions' }, retryButton, clearButton),
  );

  // Successive camera shots form one capture session (the server infers
  // missing page numbers from neighbors within a session).
  let cameraSession = null;
  let frame = 0;
  let doneCount = uploads.items(documentId).filter((item) => item.state === 'done').length;

  pickButton.addEventListener('click', () => filesInput.click());
  cameraButton.addEventListener('click', () => cameraInput.click());
  filesInput.addEventListener('change', () => {
    // File names from cameras and scanners sort in shooting order.
    const files = [...filesInput.files].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
    filesInput.value = '';
    if (files.length) uploads.add(documentId, files, { sessionId: randomUuid() });
  });
  cameraInput.addEventListener('change', () => {
    const files = [...cameraInput.files];
    cameraInput.value = '';
    if (!files.length) return;
    cameraSession ??= { id: randomUuid(), nextSeq: 1 };
    uploads.add(documentId, files, { sessionId: cameraSession.id, firstSeq: cameraSession.nextSeq });
    cameraSession.nextSeq += files.length;
  });
  retryButton.addEventListener('click', () => uploads.retryFailed(documentId));
  clearButton.addEventListener('click', () => uploads.clearFinished(documentId));

  function render() {
    frame = 0;
    const items = uploads.items(documentId);
    panel.hidden = items.length === 0;
    if (!items.length) return;

    const byState = (state) => items.filter((item) => item.state === state);
    const sent = byState('done').length;
    const failed = byState('failed');
    const rejected = byState('rejected');
    const uploading = byState('uploading');
    const waiting = byState('pending').length;
    const accepted = items.length - rejected.length;
    const busy = uploading.length + waiting > 0;

    const totalBytes = items.reduce((total, item) => total + (item.state === 'rejected' ? 0 : item.size), 0);
    const sentBytes = items.reduce((total, item) => {
      if (item.state === 'done') return total + item.size;
      if (item.state === 'uploading') return total + item.size * item.progress;
      return total;
    }, 0);
    progress.value = totalBytes ? sentBytes / totalBytes : 1;
    progress.hidden = !busy;

    const failures = failed.length + rejected.length;
    if (busy) {
      headline.textContent = t('Uploading: {sent} / {total} ({percent})', {
        sent,
        total: tn('{count} photo', '{count} photos', accepted),
        percent: formatPercent(progress.value),
      });
    } else {
      const sentPhotos = tn('{count} photo sent', '{count} photos sent', sent);
      headline.textContent = failures
        ? t('Upload finished: {sent}, {failures}', {
            sent: sentPhotos,
            failures: tn('{count} failure', '{count} failures', failures),
          })
        : t('Upload finished: {sent}', { sent: sentPhotos });
    }

    const rows = [
      ...uploading.map((item) =>
        h(
          'li',
          { class: 'upload-item' },
          h('span', { class: 'upload-name' }, item.name),
          h(
            'span',
            { class: 'upload-state' },
            t('{percent} of {size}', { percent: formatPercent(item.progress), size: formatBytes(item.size) }),
          ),
        ),
      ),
      ...[...failed, ...rejected].map((item) =>
        h(
          'li',
          { class: 'upload-item is-error' },
          h('span', { class: 'upload-name' }, item.name),
          h('span', { class: 'upload-state' }, item.error),
        ),
      ),
    ];
    if (waiting) {
      rows.push(
        h(
          'li',
          { class: 'upload-item is-muted' },
          tn('{count} photo waiting to be uploaded', '{count} photos waiting to be uploaded', waiting),
        ),
      );
    }
    list.replaceChildren(...rows);
    list.hidden = rows.length === 0;
    retryButton.hidden = failed.length === 0;
    clearButton.hidden = busy;
  }

  function onChange(event) {
    if (event.detail.documentId !== documentId) return;
    const nowDone = uploads.items(documentId).filter((item) => item.state === 'done').length;
    if (nowDone > doneCount) onUploaded();
    doneCount = nowDone;
    render();
  }

  function onProgress(event) {
    if (event.detail.documentId === documentId && !frame) frame = requestAnimationFrame(render);
  }

  uploads.addEventListener('change', onChange);
  uploads.addEventListener('progress', onProgress);
  render();

  return {
    element: h(
      'div',
      { class: 'uploader' },
      h('div', { class: 'button-row' }, pickButton, cameraButton),
      h(
        'p',
        { class: 'hint' },
        t('JPEG, PNG or WebP, 40 MiB maximum per photo. Photos are uploaded in the order of their file names.'),
      ),
      filesInput,
      cameraInput,
      panel,
    ),
    destroy() {
      uploads.removeEventListener('change', onChange);
      uploads.removeEventListener('progress', onProgress);
      cancelAnimationFrame(frame);
    },
  };
}

export function mountDocument(root, { route, signal, monitor, setTitle }) {
  const documentId = route.id;
  let doc = null;
  let loading = null;
  let reloadQueued = false;
  let refreshTimer = 0;
  let uploadRefreshTimer = 0;
  // From the last known status: a page processed before the first poll after opening is not missed.
  let lastQueueKey = queueKey(monitor.status);
  let organizer = null; // set while the pages are being organized
  // An order change and a refresh can cross: a refresh started before the
  // change, or answered while it is sent, would bring the old order back.
  let orderWrites = 0;
  let orderVersion = 0;
  let reloadAfterWrites = false;
  const pageCards = new NodeCache();
  const groupSections = new Map();

  const view = h('section', { class: 'view document-view' }, loadingState());
  root.replaceChildren(view);

  // Elements updated in place by render(), so focus survives refreshes.
  const title = h('h1', { tabindex: '-1' });
  const meta = h('ul', { class: 'chips doc-meta', role: 'list' });
  const author = h('p', { class: 'doc-author' });
  const notes = h('p', { class: 'doc-notes' });
  const readLink = h(
    'a',
    { class: 'btn btn-primary', href: href(paths.reader(documentId)) },
    icon('book'),
    t('Read document'),
  );
  const editButton = h('button', { type: 'button', class: 'btn' }, icon('edit'), t('Edit'));
  const deleteButton = h('button', { type: 'button', class: 'btn btn-danger' }, icon('trash'), t('Delete'));
  const coverage = h('div');
  const stats = h('dl', { class: 'stats' });
  const markdownLink = h('a', { class: 'btn', href: links.markdown(documentId) }, icon('download'), 'document.md');
  const zipLink = h(
    'a',
    { class: 'btn', href: links.exportZip(documentId, false) },
    icon('archive'),
    t('.zip archive'),
  );
  const withScansId = uniqueId('with-scans');
  const withScans = h('input', { type: 'checkbox', id: withScansId });
  const folder = h('code', { class: 'path' });
  const copyFolderButton = h(
    'button',
    {
      type: 'button',
      class: 'btn btn-icon btn-small',
      'aria-label': t('Copy the folder path'),
    },
    icon('copy'),
  );
  const pagesCount = h('span', { class: 'section-count' });
  const organizeButton = h(
    'button',
    { type: 'button', class: 'btn btn-small', hidden: true },
    icon('reorder'),
    t('Organize'),
  );
  const pagesHeader = h(
    'div',
    { class: 'section-header' },
    h('h2', { id: 'pages-title', class: 'section-title' }, t('Pages'), ' ', pagesCount),
    organizeButton,
  );
  const pagesBody = h('div', { class: 'page-groups' });
  const pagesSection = h(
    'section',
    { class: 'pages-section', 'aria-labelledby': 'pages-title' },
    pagesHeader,
    pagesBody,
  );
  const noPages = emptyState({
    iconName: 'camera',
    title: t('No pages yet'),
    message: t('Import photos above, or scan this document with the Android app.'),
  });
  const uploader = createUploader(documentId, { onUploaded: scheduleUploadRefresh });

  const layout = [
    h(
      'nav',
      { class: 'breadcrumb', 'aria-label': t('Breadcrumb') },
      h('a', { href: href(paths.library()) }, icon('chevron-left'), t('Library')),
    ),
    h(
      'header',
      { class: 'doc-header' },
      h('div', { class: 'view-heading' }, title, author, meta, notes),
      h('div', { class: 'view-actions' }, readLink, editButton, deleteButton),
    ),
    h(
      'div',
      { class: 'doc-overview' },
      h(
        'section',
        { class: 'card', 'aria-labelledby': 'coverage-title' },
        h('h2', { id: 'coverage-title', class: 'card-title' }, t('Coverage')),
        coverage,
        stats,
      ),
      h(
        'div',
        { class: 'doc-side' },
        h(
          'section',
          { class: 'card', 'aria-labelledby': 'upload-title' },
          h('h2', { id: 'upload-title', class: 'card-title' }, t('Add pages')),
          uploader.element,
        ),
        h(
          'section',
          { class: 'card', 'aria-labelledby': 'export-title' },
          h('h2', { id: 'export-title', class: 'card-title' }, t('Export')),
          h('div', { class: 'button-row' }, markdownLink, zipLink),
          h(
            'label',
            { class: 'checkbox checkbox-inline', for: withScansId },
            withScans,
            h('span', {}, t('Include the original photos in the archive')),
          ),
          h(
            'div',
            { class: 'folder-path' },
            h('span', { class: 'hint' }, t('Folder on the PC')),
            h('div', { class: 'copy-line' }, folder, copyFolderButton),
          ),
        ),
      ),
    ),
    pagesSection,
  ];

  function renderHeader() {
    setTitle(doc.title);
    title.textContent = doc.title;
    author.textContent = doc.author || '';
    author.hidden = !doc.author;
    setChildren(
      meta,
      h('li', { class: 'chip' }, documentKind(doc.kind)),
      doc.unwarp && h('li', { class: 'chip chip-accent' }, t('Curved pages flattened')),
    );
    notes.textContent = doc.notes || '';
    notes.hidden = !doc.notes;
  }

  function renderOverview() {
    coverage.replaceChildren(renderCoverage(doc.coverage));
    stats.replaceChildren(...statTiles(doc.stats));
    markdownLink.setAttribute('download', `${doc.slug}.md`);
    zipLink.setAttribute('download', `${doc.slug}.zip`);
    folder.textContent = doc.folder ?? '';
    folder.closest('.folder-path').hidden = !doc.folder;
  }

  function groupSection(key) {
    let section = groupSections.get(key);
    if (!section) {
      const heading = h('h3', { class: 'page-group-title' });
      const hint = h('p', { class: 'page-group-hint' });
      const list = h('ul', { class: 'page-grid', role: 'list' });
      const element = h(
        'section',
        { class: 'page-group' },
        h('div', { class: 'page-group-header' }, heading, hint),
        list,
      );
      section = { element, heading, hint, list };
      groupSections.set(key, section);
    }
    return section;
  }

  function renderPages() {
    const pages = doc.pages ?? [];
    pagesCount.textContent = pages.length ? `(${pages.length})` : '';
    organizeButton.hidden = Boolean(organizer) || pages.filter((page) => page.in_document).length < 2;
    if (organizer) {
      syncChildren(pagesSection, [pagesHeader, organizer.element]);
      organizer.update(doc);
      return;
    }
    syncChildren(pagesSection, [pagesHeader, pagesBody]);
    if (!pages.length) {
      syncChildren(pagesBody, [noPages]);
      return;
    }

    // Consecutive pages of the same kind form a group (API order is kept).
    const groups = [];
    for (const page of pages) {
      const kind = groupOf(page);
      if (groups.at(-1)?.kind !== kind) groups.push({ kind, pages: [] });
      groups.at(-1).pages.push(page);
    }
    const hasPlaced = groups.some((group) => group.kind === 'placed');
    const handPlaced = pages.some((page) => page.in_document && page.placement === 'manual');
    const seen = new Map();
    const sections = groups.map((group) => {
      const occurrence = seen.get(group.kind) ?? 0;
      seen.set(group.kind, occurrence + 1);
      const section = groupSection(occurrence ? `${group.kind}-${occurrence}` : group.kind);
      let info = PAGE_GROUPS[group.kind]();
      if (group.kind === 'unplaced' && !hasPlaced) {
        info = { title: t('In the document'), hint: t('No numbered page: capture order.') };
      } else if (group.kind === 'placed' && handPlaced) {
        info = { ...info, hint: t('In the reading order of document.md, with pages placed by hand.') };
      }
      section.heading.textContent = `${info.title} (${group.pages.length})`;
      section.hint.textContent = info.hint;
      const cards = group.pages.map((page) =>
        pageCards.get(page.id, pageSignature(page, hasPlaced), () => pageCard(page, hasPlaced)),
      );
      syncChildren(section.list, cards);
      return section.element;
    });
    pageCards.prune();
    syncChildren(pagesBody, sections);
  }

  function render() {
    if (view.firstChild?.classList.contains('state')) view.replaceChildren(...layout);
    renderHeader();
    renderOverview();
    renderPages();
  }

  async function fetchAndRender() {
    clearTimeout(refreshTimer);
    const version = orderVersion;
    try {
      const fresh = await api.getDocument(documentId, { signal });
      if (orderWrites) {
        reloadAfterWrites = true;
      } else if (version !== orderVersion) {
        reloadQueued = true; // older than the order just saved: load again
      } else {
        doc = fresh;
        render();
      }
    } catch (error) {
      if (isAbort(error)) return;
      if (!doc) {
        const notFound = error.status === 404;
        view.replaceChildren(
          errorState({
            title: notFound ? t('Document not found') : t('Could not load'),
            message: notFound ? t('This document does not exist or has been deleted.') : errorMessage(error),
            onRetry: notFound ? null : load,
            actions: [h('a', { class: 'btn', href: href(paths.library()) }, t('Back to the library'))],
          }),
        );
        return;
      }
      if (error.status === 404) {
        toast(t('This document has been deleted.'), { tone: 'error' });
        navigate(paths.library(), { replace: true });
        return;
      }
      // Transient failure: keep showing the last data and try again later.
    }
    scheduleRefresh();
  }

  /** Loads the document; calls made while a load runs trigger one more load afterwards. */
  function load() {
    if (loading) {
      reloadQueued = true;
      return;
    }
    loading = fetchAndRender().finally(() => {
      loading = null;
      if (reloadQueued && !signal.aborted) {
        reloadQueued = false;
        load();
      }
    });
  }

  /** Sends an order change (organizer) and shows the document it returns. */
  async function writeOrder(request) {
    orderWrites += 1;
    orderVersion += 1;
    try {
      doc = await request();
      render();
    } finally {
      orderWrites -= 1;
      if (!orderWrites && reloadAfterWrites) {
        reloadAfterWrites = false;
        load();
      }
    }
  }

  function startOrganizing() {
    if (organizer || !doc) return;
    organizer = createPageOrganizer({
      save: (pageIds) => writeOrder(() => api.reorderPages(documentId, pageIds)),
      reset: () => writeOrder(() => api.resetPageOrder(documentId)),
      reload: load,
      onDone: stopOrganizing,
    });
    renderPages();
    organizer.focus();
  }

  function stopOrganizing() {
    if (!organizer) return;
    organizer.destroy();
    organizer = null;
    renderPages();
    (organizeButton.hidden ? title : organizeButton).focus();
  }

  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    if (signal.aborted || !doc) return;
    const ocrPending = doc.stats.queued > 0 || doc.stats.processing > 0;
    if (ocrPending || uploads.isBusy(documentId)) refreshTimer = setTimeout(load, REFRESH_INTERVAL_MS);
  }

  /** New pages appear in the grid shortly after their upload (batched). */
  function scheduleUploadRefresh() {
    clearTimeout(uploadRefreshTimer);
    uploadRefreshTimer = setTimeout(load, 400);
  }

  /** Pages uploaded by the phone or finished by the OCR show up without polling. */
  function onStatusChange() {
    const key = queueKey(monitor.status);
    if (key === null) return;
    if (lastQueueKey !== null && key !== lastQueueKey) load();
    lastQueueKey = key;
  }

  async function editDocument() {
    const updated = await documentDialog({
      heading: t('Edit document'),
      submitLabel: t('Save'),
      initial: doc,
      withNotes: true,
      onSubmit: (values) => api.updateDocument(documentId, values),
    });
    if (!updated) return;
    doc = { ...doc, ...updated, pages: doc.pages };
    render();
    toast(t('Details saved.'), { tone: 'success' });
  }

  async function deleteDocument() {
    const confirmed = await confirmDialog({
      title: t('Delete {title}?', { title: quoted(doc.title) }),
      message: t(
        'Its folder (Markdown, illustrations and photos) will be moved to the library’s trash (.trash): ' +
          'nothing is permanently erased.',
      ),
      confirmLabel: t('Delete document'),
      danger: true,
    });
    if (!confirmed) return;
    try {
      await api.deleteDocument(documentId);
      toast(t('Document {title} moved to the trash.', { title: quoted(doc.title) }), { tone: 'success' });
      navigate(paths.library(), { replace: true });
    } catch (error) {
      toast(errorMessage(error, t('Could not delete.')), { tone: 'error' });
    }
  }

  editButton.addEventListener('click', editDocument);
  organizeButton.addEventListener('click', startOrganizing);
  deleteButton.addEventListener('click', deleteDocument);
  withScans.addEventListener('change', () => {
    zipLink.href = links.exportZip(documentId, withScans.checked);
  });
  copyFolderButton.addEventListener('click', async () => {
    const copied = await copyText(doc.folder);
    toast(copied ? t('Folder path copied.') : t('Could not copy: select the path by hand.'), {
      tone: copied ? 'success' : 'error',
    });
  });
  monitor.addEventListener('change', onStatusChange);
  load();

  return () => {
    clearTimeout(refreshTimer);
    clearTimeout(uploadRefreshTimer);
    monitor.removeEventListener('change', onStatusChange);
    uploader.destroy();
    organizer?.destroy();
  };
}
