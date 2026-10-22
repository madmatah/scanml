/**
 * Page: the original scan next to the OCR result, page number correction,
 * rotation, exclusion, OCR re-run and deletion, with previous/next
 * navigation in the document's reading order.
 */
import { api, NetworkError, versionedUrl } from '../api.js';
import { confirmDialog } from '../components/dialogs.js';
import { icon } from '../components/icons.js';
import { placementChip } from '../components/page-organizer.js';
import { errorState, loadingState } from '../components/states.js';
import { toast } from '../components/toast.js';
import { copyText } from '../lib/clipboard.js';
import { h, isTypingTarget, setChildren, uniqueId } from '../lib/dom.js';
import { errorMessage, isAbort } from '../lib/errors.js';
import { formatDateTime, formatSeconds, quoted } from '../lib/format.js';
import { t, tc, tn } from '../lib/i18n.js';
import { numberSource, pageShortLabel, pageStatus, pageTitle } from '../lib/labels.js';
import { renderMath } from '../lib/math.js';
import { localizeMarkers } from '../lib/reading.js';
import { href, navigate, paths } from '../router.js';

const POLL_INTERVAL_MS = 3000;

/** Space kept under the sticky header when fitting the scan to the screen, in px. */
const FIT_MARGIN_PX = 112;

const isPresent = (value) => value !== null && value !== undefined;

/**
 * Buttons are marked aria-disabled rather than disabled: a disabled button
 * loses keyboard focus, which would happen to the very button just used.
 */
function setUnavailable(button, unavailable) {
  if (unavailable) button.setAttribute('aria-disabled', 'true');
  else button.removeAttribute('aria-disabled');
}

/** Button showing only an icon; the label is its accessible name and its tooltip. */
function iconButton(iconName, label) {
  return h('button', { type: 'button', class: 'btn btn-icon', 'aria-label': label, title: label }, icon(iconName));
}

/** Click listener that ignores clicks while the button is aria-disabled. */
function onActivate(button, handler) {
  button.addEventListener('click', (event) => {
    if (button.getAttribute('aria-disabled') !== 'true') handler(event);
  });
}

function detailRows(page) {
  const source = numberSource(page.number_source);
  const ocr = page.ocr ?? {};
  const none = tc('page number', 'none');
  const rows = [
    [t('Status'), pageStatus(page.status).label],
    [t('Number'), page.page_label ? `${page.page_label}${source ? ` (${source.label})` : ''}` : none],
    [t('Numbers read on the page'), page.detected_numbers?.length ? page.detected_numbers.join(', ') : none],
    [t('Number given by the phone'), page.hint_number],
    [t('Captured'), formatDateTime(page.captured_at)],
    [t('Received'), formatDateTime(page.uploaded_at)],
    [
      t('Photo series'),
      page.session_id
        ? t('{series} · photo no. {seq}', { series: page.session_id.slice(0, 8), seq: page.seq ?? '—' })
        : null,
    ],
    [t('Rotation'), `${page.rotation ?? 0}°`],
    [t('Dimensions'), page.width && page.height ? `${page.width} × ${page.height} px` : null],
    [t('Text recognition engine'), ocr.engine],
    [t('Text recognition time'), isPresent(ocr.duration_s) ? formatSeconds(ocr.duration_s) : null],
    [t('Recognized text'), isPresent(ocr.chars) ? tn('{count} character', '{count} characters', ocr.chars) : null],
    [t('Illustrations'), isPresent(ocr.images) ? String(ocr.images) : null],
    [t('Text read on'), ocr.at ? formatDateTime(ocr.at) : null],
    [t('File key'), page.key && h('code', {}, page.key)],
  ];
  return rows
    .filter(([, value]) => isPresent(value) && value !== '')
    .map(([term, value]) => h('div', {}, h('dt', {}, term), h('dd', {}, value)));
}

function numberHelp(page) {
  const source = numberSource(page.number_source);
  if (!source && page.placement === 'manual') {
    return t('No known number: the page is at the place chosen with “Organize”.');
  }
  if (!source && page.placement === 'session') {
    return t('No known number: the page is placed next to the pages photographed just before or just after it.');
  }
  if (!source) return t('No known number: the page is filed with the unnumbered pages, at the end of the document.');
  if (page.number_source === 'manual') {
    return t('Typed by hand. {clear} goes back to the detected or inferred number.', { clear: quoted(t('Clear')) });
  }
  return `${source.description}.`;
}

export function mountPage(root, { route, signal, setTitle }) {
  const pageId = route.id;
  let page = null;
  let doc = null;
  let html = '';
  let neighbors = { previous: null, next: null };
  let showMarkdown = false;
  let fullWidth = false;
  let busy = false;
  let loading = null;
  let reloadQueued = false;
  let pollTimer = 0;
  let layoutFrame = 0;
  let lastViewportWidth = 0;

  const view = h('section', { class: 'view page-view' }, loadingState());
  root.replaceChildren(view);

  // Elements are created once and updated in place, so that keyboard focus
  // stays on the control that was just used.
  const documentLink = h('a', {});
  const currentCrumb = h('span', { 'aria-current': 'page' });
  const title = h('h1', { tabindex: '-1' });
  const headerChips = h('ul', { class: 'chips', role: 'list' });
  const previousLink = h(
    'a',
    { class: 'btn', rel: 'prev' },
    icon('chevron-left'),
    h('span', { class: 'btn-label' }, t('Previous')),
  );
  const nextLink = h(
    'a',
    { class: 'btn', rel: 'next' },
    h('span', { class: 'btn-label' }, t('Next')),
    icon('chevron-right'),
  );
  const position = h('span', { class: 'pager-position' });
  const notices = h('div', { class: 'page-notices' });

  const numberId = uniqueId('page-number');
  const numberHelpId = uniqueId('page-number-help');
  const numberInput = h('input', {
    id: numberId,
    type: 'number',
    inputmode: 'numeric',
    min: 1,
    max: 9999,
    step: 1,
    class: 'input input-number',
    'aria-describedby': numberHelpId,
  });
  const saveNumberButton = h('button', { type: 'submit', class: 'btn' }, icon('check'), t('Save'));
  const clearNumberButton = h('button', { type: 'button', class: 'btn btn-ghost' }, t('Clear'));
  const numberHint = h('p', { id: numberHelpId, class: 'hint' });
  const numberForm = h(
    'form',
    { class: 'number-form', novalidate: true },
    h('label', { for: numberId, class: 'field-label' }, t('Page number')),
    h('div', { class: 'number-controls' }, numberInput, saveNumberButton, clearNumberButton),
    numberHint,
  );

  const rotateLeftButton = iconButton('rotate-left', t('Rotate 90° to the left'));
  const rotateRightButton = iconButton('rotate-right', t('Rotate 90° to the right'));
  const rotateLabelId = uniqueId('rotate-label');
  const excludeButton = h('button', { type: 'button', class: 'btn' });
  const reprocessButton = h('button', { type: 'button', class: 'btn' }, icon('refresh'), t('Read the text again'));
  const deleteButton = h('button', { type: 'button', class: 'btn btn-danger' }, icon('trash'), t('Delete'));

  const scanImage = h('img', { alt: '', decoding: 'async' });
  const scanFrame = h('div', { class: 'scan-frame' }, scanImage);
  const scanViewport = h('div', { class: 'scan-viewport' }, scanFrame);
  const zoomButton = h(
    'button',
    { type: 'button', class: 'btn btn-small', 'aria-pressed': 'false' },
    icon('expand'),
    t('Full width'),
  );
  const originalLink = h(
    'a',
    { class: 'btn btn-small btn-ghost', target: '_blank', rel: 'noopener' },
    icon('external'),
    t('Original'),
  );
  const markdownToggle = h(
    'button',
    { type: 'button', class: 'btn btn-small', 'aria-pressed': 'false' },
    t('Raw Markdown'),
  );
  const copyButton = h('button', { type: 'button', class: 'btn btn-small btn-ghost' }, icon('copy'), t('Copy'));
  const textBody = h('div', { class: 'text-body' });
  const details = h('dl', { class: 'details-list' });

  const actionButtons = [
    saveNumberButton,
    clearNumberButton,
    rotateLeftButton,
    rotateRightButton,
    excludeButton,
    reprocessButton,
    deleteButton,
  ];

  const layout = [
    h(
      'nav',
      { class: 'breadcrumb', 'aria-label': t('Breadcrumb') },
      h('a', { href: href(paths.library()) }, t('Library')),
      h('span', { class: 'breadcrumb-separator', 'aria-hidden': 'true' }, '›'),
      documentLink,
      h('span', { class: 'breadcrumb-separator', 'aria-hidden': 'true' }, '›'),
      currentCrumb,
    ),
    h(
      'header',
      { class: 'page-header' },
      h('div', { class: 'page-heading' }, title, headerChips),
      h('nav', { class: 'pager', 'aria-label': t('Document pages') }, previousLink, position, nextLink),
    ),
    notices,
    h(
      'section',
      { class: 'card page-toolbar', 'aria-label': t('Page actions') },
      numberForm,
      h(
        'div',
        { class: 'button-row page-actions' },
        h(
          'div',
          { class: 'rotate-group', role: 'group', 'aria-labelledby': rotateLabelId },
          h('span', { id: rotateLabelId, class: 'rotate-group-label' }, t('Rotate')),
          rotateLeftButton,
          rotateRightButton,
        ),
        excludeButton,
        reprocessButton,
        deleteButton,
      ),
    ),
    h(
      'div',
      { class: 'page-split' },
      h(
        'section',
        { class: 'pane scan-pane', 'aria-labelledby': 'scan-title' },
        h(
          'div',
          { class: 'pane-header' },
          h('h2', { id: 'scan-title', class: 'pane-title' }, t('Scan')),
          h('div', { class: 'pane-tools' }, zoomButton, originalLink),
        ),
        scanViewport,
      ),
      h(
        'section',
        { class: 'pane text-pane', 'aria-labelledby': 'text-title' },
        h(
          'div',
          { class: 'pane-header' },
          h('h2', { id: 'text-title', class: 'pane-title' }, t('Recognized text')),
          h('div', { class: 'pane-tools' }, markdownToggle, copyButton),
        ),
        textBody,
      ),
    ),
    h('details', { class: 'card page-details' }, h('summary', {}, t('Technical details')), details),
  ];

  /** Sizes the scan for its rotation: whole page on screen, or full pane width. */
  function layoutScan() {
    layoutFrame = 0;
    const { naturalWidth: width, naturalHeight: height } = scanImage;
    if (!page || !width || !height) return;
    const quarterTurn = (page.rotation ?? 0) % 180 !== 0;
    const shownWidth = quarterTurn ? height : width;
    const shownHeight = quarterTurn ? width : height;
    const header = document.getElementById('app-header');
    const maxHeight = fullWidth
      ? Infinity
      : Math.max(240, window.innerHeight - (header?.offsetHeight ?? 0) - FIT_MARGIN_PX);
    lastViewportWidth = scanViewport.clientWidth;
    const scale = Math.min(lastViewportWidth / shownWidth, maxHeight / shownHeight);
    scanFrame.style.width = `${shownWidth * scale}px`;
    scanFrame.style.height = `${shownHeight * scale}px`;
    scanImage.style.width = `${width * scale}px`;
    scanImage.style.height = `${height * scale}px`;
    scanImage.style.transform = `translate(-50%, -50%) rotate(${page.rotation ?? 0}deg)`;
  }

  // Layout runs in the next frame: resizing synchronously inside the
  // observer would re-trigger it within the same frame.
  const scheduleLayout = () => {
    layoutFrame ||= requestAnimationFrame(layoutScan);
  };
  const resizeObserver = new ResizeObserver(() => {
    if (scanViewport.clientWidth !== lastViewportWidth) scheduleLayout();
  });

  function setLink(link, target) {
    if (target) {
      link.href = href(paths.page(target.id));
      link.title = pageShortLabel(target);
      link.removeAttribute('aria-disabled');
    } else {
      link.removeAttribute('href');
      link.removeAttribute('title');
      link.setAttribute('aria-disabled', 'true');
    }
  }

  function updateControls() {
    for (const button of actionButtons) setUnavailable(button, busy);
    setUnavailable(clearNumberButton, busy || !isPresent(page?.manual_number));
    setUnavailable(reprocessButton, busy || page?.status === 'queued' || page?.status === 'processing');
    setUnavailable(copyButton, !page?.markdown?.trim());
  }

  function setBusy(value) {
    busy = value;
    updateControls();
  }

  function renderNotices() {
    const items = [];
    if (page.status === 'error') {
      items.push(
        h(
          'div',
          { class: 'notice notice-danger' },
          icon('alert'),
          h(
            'p',
            {},
            h('strong', {}, t('Couldn’t read the text.')),
            ' ',
            t('You can read the text again or rotate the page.'),
            page.error && h('span', { class: 'notice-detail' }, t('Details: {error}', { error: page.error })),
          ),
        ),
      );
    }
    if (page.duplicate_of) {
      items.push(
        h(
          'div',
          { class: 'notice notice-warn' },
          icon('copy'),
          h(
            'p',
            {},
            h('strong', {}, t('Duplicate.')),
            ' ',
            t('A newer scan has the same number and replaces it in the document.'),
            ' ',
            h('a', { href: href(paths.page(page.duplicate_of)) }, t('See the page kept')),
          ),
        ),
      );
    }
    if (page.excluded) {
      items.push(
        h(
          'div',
          { class: 'notice' },
          icon('eye-off'),
          h('p', {}, h('strong', {}, t('Page excluded.')), ' ', t('It does not appear in document.md.')),
        ),
      );
    }
    notices.replaceChildren(...items);
    notices.hidden = items.length === 0;
  }

  function renderText() {
    markdownToggle.setAttribute('aria-pressed', String(showMarkdown));
    const hasMarkdown = Boolean(page.markdown?.trim());

    if (page.status === 'queued' || page.status === 'processing') {
      textBody.replaceChildren(
        h(
          'div',
          { class: 'state state-loading', role: 'status' },
          h('span', { class: 'spinner', 'aria-hidden': 'true' }),
          h('span', {}, page.status === 'queued' ? t('Waiting to be read…') : t('Reading…')),
        ),
      );
    } else if (page.status === 'error' && !hasMarkdown) {
      textBody.replaceChildren(h('p', { class: 'state' }, t('No text: this page couldn’t be read.')));
    } else if (showMarkdown) {
      textBody.replaceChildren(
        hasMarkdown
          ? h('pre', { class: 'markdown-source' }, page.markdown)
          : h('p', { class: 'state' }, t('Empty Markdown.')),
      );
    } else if (html.trim()) {
      // Sanitized by the server (allowlist sanitizer), and the CSP forbids
      // inline scripts: this is the only HTML the UI inserts as-is. It is
      // parsed in an inert template first, so that illustration URLs get the
      // OCR version before anything loads (a new OCR rewrites them in place).
      // Markers the server may generate are written in the UI language, and its
      // formulas, marked by the server, are then typeset by KaTeX.
      const template = document.createElement('template');
      template.innerHTML = html;
      localizeMarkers(template.content);
      for (const image of template.content.querySelectorAll('img[src]')) {
        image.setAttribute('src', versionedUrl(image.getAttribute('src'), page.ocr?.at ?? ''));
      }
      textBody.replaceChildren(h('div', { class: 'ocr-render' }, template.content));
      renderMath(textBody);
    } else {
      textBody.replaceChildren(h('p', { class: 'state' }, t('No text recognized on this page.')));
    }
  }

  function renderScan() {
    scanImage.alt = t('Original scan, {page}', { page: pageTitle(page).toLowerCase() });
    if (scanImage.getAttribute('src') !== page.image_url) scanImage.src = page.image_url;
    originalLink.href = page.image_url;
    zoomButton.setAttribute('aria-pressed', String(fullWidth));
    scanViewport.classList.toggle('is-full-width', fullWidth);
    scheduleLayout();
  }

  function render() {
    if (view.firstChild?.classList.contains('state')) {
      view.replaceChildren(...layout);
      resizeObserver.observe(scanViewport);
    }
    const heading = pageTitle(page);
    const source = numberSource(page.number_source);
    const status = pageStatus(page.status);
    setTitle(`${heading} · ${doc.title}`);

    documentLink.href = href(paths.document(doc.id));
    documentLink.textContent = doc.title;
    currentCrumb.textContent = heading;
    title.textContent = heading;
    setChildren(
      headerChips,
      source &&
        h(
          'li',
          { class: ['chip', 'chip-source', `source-${page.number_source}`], title: source.description },
          source.label,
        ),
      h('li', { class: ['chip', `chip-${status.tone}`] }, status.label),
      page.excluded && h('li', { class: 'chip chip-outline' }, tc('one page', 'Excluded')),
      page.duplicate_of && h('li', { class: 'chip chip-warn' }, t('Duplicate')),
    );

    const pages = doc.pages ?? [];
    const index = pages.findIndex((candidate) => candidate.id === page.id);
    const placement = placementChip(
      page,
      pages.some((other) => other.in_document && other.placement !== 'unplaced'),
    );
    if (placement) headerChips.append(h('li', {}, placement));
    neighbors = { previous: pages[index - 1] ?? null, next: index >= 0 ? (pages[index + 1] ?? null) : null };
    setLink(previousLink, neighbors.previous);
    setLink(nextLink, neighbors.next);
    position.textContent = index >= 0 ? `${index + 1} / ${pages.length}` : '';

    if (document.activeElement !== numberInput) {
      // Roman front-matter numbers cannot be typed in a number field.
      const arabicNumber = /^\d/.test(page.page_label ?? '') ? page.number : null;
      numberInput.value = String(page.manual_number ?? arabicNumber ?? '');
    }
    numberHint.textContent = numberHelp(page);
    excludeButton.replaceChildren(
      icon(page.excluded ? 'eye' : 'eye-off'),
      h(
        'span',
        { class: 'label-long' },
        page.excluded ? t('Put back in the document') : t('Exclude from the document'),
      ),
      h('span', { class: 'label-short' }, page.excluded ? t('Put back') : t('Exclude')),
    );

    renderNotices();
    renderScan();
    renderText();
    details.replaceChildren(...detailRows(page));
    updateControls();
  }

  async function fetchAndRender() {
    clearTimeout(pollTimer);
    try {
      page = await api.getPage(pageId, { signal });
      const [documentData, pageHtml] = await Promise.all([
        api.getDocument(page.document_id, { signal }),
        page.status === 'done' ? api.getPageHtml(pageId, { signal }) : '',
      ]);
      doc = documentData;
      html = pageHtml ?? '';
      render();
    } catch (error) {
      if (isAbort(error)) return;
      const notFound = error.status === 404;
      if (!doc || notFound) {
        view.replaceChildren(
          errorState({
            title: notFound ? t('Page not found') : t('Could not load'),
            message: notFound ? t('This page does not exist or has been deleted.') : errorMessage(error),
            onRetry: notFound ? null : load,
            actions: [h('a', { class: 'btn', href: href(paths.library()) }, t('Back to the library'))],
          }),
        );
        return;
      }
      // While the server is unreachable the banner says so; keep the last data.
      if (!(error instanceof NetworkError)) {
        toast(errorMessage(error, t('Could not refresh the page.')), { tone: 'error' });
      }
    }
    if (page?.status === 'queued' || page?.status === 'processing') {
      pollTimer = setTimeout(load, POLL_INTERVAL_MS);
    }
  }

  /** Loads everything; a call made during a load triggers one more load afterwards. */
  function load() {
    if (loading) {
      reloadQueued = true;
      return loading;
    }
    loading = fetchAndRender().finally(() => {
      loading = null;
      if (reloadQueued && !signal.aborted) {
        reloadQueued = false;
        load();
      }
    });
    return loading;
  }

  /** Runs an API action, reports it, then reloads the page and the document. */
  async function act(action, successMessage) {
    if (busy) return;
    setBusy(true);
    try {
      await action();
      toast(successMessage, { tone: 'success' });
    } catch (error) {
      if (isAbort(error)) return;
      toast(errorMessage(error, t('Action failed.')), { tone: 'error' });
    } finally {
      setBusy(false);
    }
    await load();
  }

  numberForm.addEventListener('submit', (event) => {
    event.preventDefault();
    if (busy) return;
    const value = Number(numberInput.value);
    if (!numberInput.value.trim() || !Number.isInteger(value) || value < 1 || value > 9999) {
      toast(t('Enter a whole page number between 1 and 9999.'), { tone: 'error' });
      numberInput.focus();
      return;
    }
    act(() => api.updatePage(pageId, { manual_number: value }), t('Number {number} saved.', { number: value }));
  });
  onActivate(clearNumberButton, () => {
    act(() => api.updatePage(pageId, { manual_number: null }), t('Manual number cleared.'));
  });
  onActivate(rotateLeftButton, () => {
    act(
      () => api.updatePage(pageId, { rotation: ((page.rotation ?? 0) + 270) % 360 }),
      t('Page rotated: its text will be read again.'),
    );
  });
  onActivate(rotateRightButton, () => {
    act(
      () => api.updatePage(pageId, { rotation: ((page.rotation ?? 0) + 90) % 360 }),
      t('Page rotated: its text will be read again.'),
    );
  });
  onActivate(excludeButton, () => {
    const exclude = !page.excluded;
    act(
      () => api.updatePage(pageId, { excluded: exclude }),
      exclude ? t('Page excluded from the document.') : t('Page put back in the document.'),
    );
  });
  onActivate(reprocessButton, () => {
    act(() => api.reprocessPage(pageId), t('The text of this page will be read again.'));
  });
  onActivate(deleteButton, async () => {
    const confirmed = await confirmDialog({
      title: t('Delete this page?'),
      message: t(
        'The scan, its text and its illustrations will be moved to the library’s trash (.trash), ' +
          'then the document will be reassembled.',
      ),
      confirmLabel: t('Delete page'),
      danger: true,
    });
    if (!confirmed) return;
    const destination = neighbors.next ?? neighbors.previous;
    setBusy(true);
    try {
      await api.deletePage(pageId);
      toast(t('Page deleted.'), { tone: 'success' });
      navigate(destination ? paths.page(destination.id) : paths.document(page.document_id), { replace: true });
    } catch (error) {
      toast(errorMessage(error, t('Could not delete.')), { tone: 'error' });
      setBusy(false);
    }
  });
  zoomButton.addEventListener('click', () => {
    fullWidth = !fullWidth;
    renderScan();
  });
  markdownToggle.addEventListener('click', () => {
    showMarkdown = !showMarkdown;
    renderText();
  });
  onActivate(copyButton, async () => {
    const copied = await copyText(page.markdown ?? '');
    toast(copied ? t('Markdown copied.') : t('Could not copy.'), { tone: copied ? 'success' : 'error' });
  });
  scanImage.addEventListener('load', scheduleLayout);

  function onKeydown(event) {
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (isTypingTarget(event.target) || document.querySelector('dialog[open]')) return;
    const target = { ArrowLeft: neighbors.previous, ArrowRight: neighbors.next }[event.key];
    if (!target) return;
    event.preventDefault();
    navigate(paths.page(target.id));
  }

  window.addEventListener('resize', scheduleLayout);
  document.addEventListener('keydown', onKeydown);
  load();

  return () => {
    clearTimeout(pollTimer);
    cancelAnimationFrame(layoutFrame);
    resizeObserver.disconnect();
    window.removeEventListener('resize', scheduleLayout);
    document.removeEventListener('keydown', onKeydown);
  };
}
