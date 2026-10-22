/**
 * Reading view: the whole document in reading order, as in document.md
 * (GET /api/documents/{id}/html, sanitized by the server), with its
 * generated markers in the UI language and its formulas typeset. A discreet
 * marker at the start of each page links to its page screen; the "Page"
 * list, which sticks under the header, follows the reading and jumps to a
 * page. Coming back to this screen (from a page screen, or after a reload)
 * returns to the page that was being read.
 */
import { api, links, versionedUrl } from '../api.js';
import { icon } from '../components/icons.js';
import { emptyState, errorState, loadingState } from '../components/states.js';
import { toast } from '../components/toast.js';
import { h, uniqueId } from '../lib/dom.js';
import { errorMessage, isAbort } from '../lib/errors.js';
import { t, tn } from '../lib/i18n.js';
import { renderMath } from '../lib/math.js';
import { localizeMarkers, pageAtLine, readingOutline } from '../lib/reading.js';
import { currentRoute, href, paths } from '../router.js';

/** The page being read is the last one whose top is less than this under the "Page" bar, in px. */
const READING_LINE_PX = 24;

/** Quiet time before the page being read is saved in the history entry, in ms. */
const REMEMBER_DELAY_MS = 300;

/** What the user does to scroll; a page jumped to is not held in place any more. */
const USER_SCROLL_EVENTS = ['wheel', 'touchstart', 'keydown', 'pointerdown'];

/**
 * Splits the document HTML into its parts (see readingOutline) and its page
 * sections, in reading order.
 */
function documentParts(content) {
  const parts = [];
  const sections = [];
  for (const element of content.children) {
    if (element.matches('section.page')) {
      const marker = element.querySelector(':scope > .page-marker');
      parts.push({ type: 'page', key: element.dataset.key ?? '', marker: marker?.textContent ?? '' });
      sections.push(element);
    } else if (element.matches('.missing-pages')) {
      parts.push({ type: 'gap', text: element.textContent });
    } else if (element.matches('.unnumbered')) {
      parts.push({ type: 'heading', text: element.textContent });
    }
  }
  return { parts, sections };
}

/** Links the marker of a page section to the page screen; illustrations load as they come into view. */
function preparePage(section, page) {
  const marker = section.querySelector(':scope > .page-marker');
  if (marker && page) {
    marker.replaceChildren(
      h(
        'a',
        {
          href: href(paths.page(page.id)),
          title: t('Open this page: scan, number, recognized text'),
        },
        marker.textContent,
      ),
    );
  }
  for (const image of section.querySelectorAll('img[src]')) {
    // A new OCR rewrites the illustrations in place (see views/page.js).
    image.setAttribute('src', versionedUrl(image.getAttribute('src'), page?.ocr?.at ?? ''));
    image.setAttribute('loading', 'lazy');
    image.setAttribute('decoding', 'async');
  }
}

function waitingPages(doc) {
  return (doc.stats?.queued ?? 0) + (doc.stats?.processing ?? 0);
}

export function mountReader(root, { route, signal, setTitle }) {
  const documentId = route.id;
  let shown = false;
  let loading = false;
  let sections = [];
  let current = -1;
  let pinned = null; // the page jumped to, held in place until the user scrolls (see goToPage)
  let trackFrame = 0;
  let rememberTimer = 0;

  const view = h('section', { class: 'view reader-view' }, loadingState(t('Loading the document…')));
  root.replaceChildren(view);

  // Elements created once: a reload ("Refresh") updates them in place.
  const documentLink = h('a', { href: href(paths.document(documentId)) });
  const titleId = uniqueId('reader-title');
  const title = h('h1', { id: titleId });
  const author = h('p', { class: 'doc-author' });
  const markdownLink = h(
    'a',
    { class: 'btn', href: links.markdown(documentId) },
    icon('download'),
    t('Download document.md'),
  );
  const notice = h('div', { class: 'notice reader-notice', role: 'status' });
  const selectId = uniqueId('reader-page');
  const pageSelect = h('select', { id: selectId, class: 'input reader-select' });
  const position = h('span', { class: 'reader-position' });
  const toolbar = h(
    'div',
    { class: 'reader-toolbar' },
    h('label', { class: 'reader-select-label', for: selectId }, t('Page')),
    pageSelect,
    position,
  );
  const text = h('article', { class: 'ocr-render reader-text', 'aria-labelledby': titleId });

  const breadcrumb = h(
    'nav',
    { class: 'breadcrumb', 'aria-label': t('Breadcrumb') },
    h('a', { href: href(paths.library()) }, t('Library')),
    h('span', { class: 'breadcrumb-separator', 'aria-hidden': 'true' }, '›'),
    documentLink,
    h('span', { class: 'breadcrumb-separator', 'aria-hidden': 'true' }, '›'),
    h('span', { 'aria-current': 'page' }, t('Reading')),
  );
  const header = h(
    'header',
    { class: 'doc-header reader-header' },
    h('div', { class: 'view-heading' }, title, author),
    h('div', { class: 'view-actions' }, markdownLink),
  );

  const backToDocument = () =>
    h('a', { class: 'btn', href: href(paths.document(documentId)) }, icon('chevron-left'), t('Back to the document'));
  const reloadButton = () =>
    h('button', { type: 'button', class: 'btn btn-small', onClick: load }, icon('refresh'), t('Refresh'));

  // The "Page" bar sticks under the sticky app header; pages jumped to stay clear of both.
  const appHeader = document.getElementById('app-header');
  function updateStickyOffsets() {
    const headerHeight = appHeader && !appHeader.hidden ? appHeader.offsetHeight : 0;
    view.style.setProperty('--reader-top', `${headerHeight}px`);
    const barTop = Number.parseFloat(getComputedStyle(toolbar).top) || 0;
    view.style.setProperty('--reader-covered', `${barTop + toolbar.offsetHeight}px`);
  }
  const resizeObserver = new ResizeObserver(updateStickyOffsets);
  if (appHeader) resizeObserver.observe(appHeader);
  resizeObserver.observe(toolbar);

  /** Saves the page being read in this screen's history entry, for "Back" and reloads. */
  function rememberPage(key) {
    clearTimeout(rememberTimer);
    const now = currentRoute();
    if (now.name !== 'reader' || now.id !== documentId) return; // the history entry is another screen's
    history.replaceState({ ...history.state, readingPage: key }, '');
  }

  function setCurrent(index) {
    if (index === current) return;
    current = index;
    pageSelect.value = String(index);
    position.textContent = `${index + 1} / ${sections.length}`;
    clearTimeout(rememberTimer);
    const { key } = sections[index].dataset;
    rememberTimer = setTimeout(() => rememberPage(key), REMEMBER_DELAY_MS);
  }

  function trackReading() {
    trackFrame = 0;
    if (!sections.length) return;
    const line = toolbar.getBoundingClientRect().bottom + READING_LINE_PX;
    if (pinned !== null) {
      // The page jumped to, even if the end of the text is too short to bring it up to
      // the line, unless the user took it off the screen (scroll bar).
      const { top, bottom } = sections[pinned].getBoundingClientRect();
      if (bottom > line && top < window.innerHeight) {
        setCurrent(pinned);
        return;
      }
      pinned = null;
    }
    const { scrollHeight } = document.documentElement;
    if (window.scrollY > 0 && window.innerHeight + window.scrollY >= scrollHeight - 2) {
      setCurrent(sections.length - 1); // the last pages may be too short to reach the line
      return;
    }
    setCurrent(pageAtLine(sections.length, (index) => sections[index].getBoundingClientRect().top, line));
  }

  const scheduleTracking = () => {
    trackFrame ||= requestAnimationFrame(trackReading);
  };

  /**
   * Shows a page at the top, and holds it there until the user scrolls: the
   * illustrations above it, loaded as they come into view, would push it down
   * or pull it up when they get their height.
   */
  function goToPage(index) {
    const section = sections[index];
    if (!section) return;
    pinned = index;
    section.scrollIntoView({ block: 'start' });
    setCurrent(index);
  }

  function holdPinnedPage(event) {
    if (pinned === null || !(event.target instanceof HTMLImageElement)) return;
    const section = sections[pinned];
    if (section.compareDocumentPosition(event.target) & Node.DOCUMENT_POSITION_PRECEDING) {
      section.scrollIntoView({ block: 'start' });
    }
  }

  const releasePinnedPage = () => {
    pinned = null;
  };

  function renderNotice(doc) {
    const waiting = waitingPages(doc);
    notice.hidden = waiting === 0;
    if (!waiting) return;
    notice.replaceChildren(
      h(
        'p',
        {},
        tn(
          '{count} page is still waiting to be read: its text will be added once ready.',
          '{count} pages are still waiting to be read: their text will be added once ready.',
          waiting,
        ),
      ),
      reloadButton(),
    );
  }

  function emptyMessage(doc) {
    if (waitingPages(doc)) return t('Its pages are still waiting to be read: their text will appear here once ready.');
    if (doc.stats?.pages) {
      return t('None of its pages is in the document: they couldn’t be read, are excluded or are duplicates.');
    }
    return t('This document has no page yet: add some from its screen or with the Android app.');
  }

  function buildPageList(outline) {
    let parent = pageSelect;
    pageSelect.replaceChildren();
    for (const entry of outline) {
      if (entry.type === 'group') {
        parent = h('optgroup', { label: entry.label });
        pageSelect.append(parent);
      } else if (entry.type === 'gap') {
        parent.append(h('option', { disabled: true }, entry.label));
      } else {
        parent.append(h('option', { value: String(entry.index) }, entry.label));
      }
    }
  }

  function render(doc, html, readingKey) {
    setTitle(`${t('Reading')} · ${doc.title}`);
    documentLink.textContent = doc.title;
    title.textContent = doc.title;
    author.textContent = doc.author || '';
    author.hidden = !doc.author;
    markdownLink.setAttribute('download', `${doc.slug}.md`);

    // Sanitized by the server (allowlist), like the page previews of views/page.js.
    const template = document.createElement('template');
    template.innerHTML = html;
    const { content } = template;
    if (content.firstElementChild?.tagName === 'H1') content.firstElementChild.remove(); // the title, shown above
    localizeMarkers(content);
    const pagesByKey = new Map((doc.pages ?? []).map((page) => [page.key, page]));
    const { parts, sections: pageSections } = documentParts(content);
    for (const section of pageSections) preparePage(section, pagesByKey.get(section.dataset.key));
    for (const gap of [...content.children].filter((element) => element.matches('.missing-pages'))) {
      gap.prepend(h('span', { class: 'swatch is-missing', 'aria-hidden': 'true' })); // as in the coverage legend
    }
    sections = pageSections;
    current = -1;
    pinned = null;
    shown = true;

    if (!sections.length) {
      const waiting = waitingPages(doc) > 0;
      view.replaceChildren(
        breadcrumb,
        header,
        emptyState({
          iconName: 'book',
          title: t('Nothing to read yet'),
          message: emptyMessage(doc),
          actions: [waiting && reloadButton(), backToDocument()].filter(Boolean),
        }),
      );
      return;
    }

    renderNotice(doc);
    buildPageList(readingOutline(parts, pagesByKey));
    view.replaceChildren(breadcrumb, header, notice, toolbar, text);
    text.replaceChildren(content);
    renderMath(text);
    updateStickyOffsets();
    const restored = readingKey ? sections.findIndex((section) => section.dataset.key === readingKey) : -1;
    if (restored >= 0) goToPage(restored);
    else trackReading();
  }

  async function load() {
    if (loading) return;
    loading = true;
    if (!shown) view.replaceChildren(loadingState(t('Loading the document…')));
    // The first load goes back to the page read in this history entry ("Back", browser
    // reload); "Refresh", at the top of the screen, stays there.
    const readingKey = shown ? null : history.state?.readingPage;
    try {
      const [doc, html] = await Promise.all([
        api.getDocument(documentId, { signal }),
        api.getDocumentHtml(documentId, { signal }),
      ]);
      render(doc, html, readingKey);
    } catch (error) {
      if (isAbort(error)) return;
      const notFound = error.status === 404;
      if (shown && !notFound) {
        toast(errorMessage(error, t('Could not refresh.')), { tone: 'error' });
        return;
      }
      shown = false;
      sections = [];
      view.replaceChildren(
        errorState({
          title: notFound ? t('Document not found') : t('Could not load'),
          message: notFound ? t('This document does not exist or has been deleted.') : errorMessage(error),
          onRetry: notFound ? null : load,
          actions: [
            notFound
              ? h('a', { class: 'btn', href: href(paths.library()) }, t('Back to the library'))
              : backToDocument(),
          ],
        }),
      );
    } finally {
      loading = false;
    }
  }

  pageSelect.addEventListener('change', () => goToPage(Number(pageSelect.value)));
  // "Back" from the page screen returns to the page whose marker was followed.
  text.addEventListener('click', (event) => {
    const section = event.target.closest?.('.page-marker a')?.closest('section.page');
    if (section) rememberPage(section.dataset.key);
  });
  text.addEventListener('load', holdPinnedPage, true); // "load" does not bubble
  window.addEventListener('scroll', scheduleTracking, { passive: true });
  window.addEventListener('resize', scheduleTracking);
  for (const type of USER_SCROLL_EVENTS) window.addEventListener(type, releasePinnedPage, { passive: true });
  load();

  return () => {
    cancelAnimationFrame(trackFrame);
    clearTimeout(rememberTimer);
    resizeObserver.disconnect();
    window.removeEventListener('scroll', scheduleTracking);
    window.removeEventListener('resize', scheduleTracking);
    for (const type of USER_SCROLL_EVENTS) window.removeEventListener(type, releasePinnedPage);
  };
}
