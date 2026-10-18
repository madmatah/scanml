/**
 * OCR engine state in the header (badge + details panel) and the warning
 * banners shown under it, both fed by the StatusMonitor.
 */
import { h, setChildren } from '../lib/dom.js';
import { formatDecimal, formatNumber, quoted } from '../lib/format.js';
import { t, tn } from '../lib/i18n.js';
import { engineState } from '../lib/labels.js';
import { icon } from './icons.js';

/** Engine state as displayed, taking the server's reachability into account. */
function displayedState(monitor) {
  if (monitor.connection === 'offline') {
    return {
      label: t('Server unreachable'),
      tone: 'danger',
      description: t('The ScanMyLib server is not responding.'),
    };
  }
  const ocr = monitor.status?.ocr;
  if (!ocr) return { label: t('OCR…'), tone: 'neutral', description: '' };
  return engineState(ocr.reachable === false ? 'unreachable' : ocr.state);
}

function gpuMemory(gpu) {
  if (typeof gpu?.memory_used_mb !== 'number' || !gpu.memory_total_mb) return null;
  const toGb = (mb) => formatDecimal(mb / 1024);
  return t('{used} / {total} GB used', { used: toGb(gpu.memory_used_mb), total: toGb(gpu.memory_total_mb) });
}

function detailRow(term, value) {
  return value === null || value === undefined || value === ''
    ? null
    : h('div', {}, h('dt', {}, term), h('dd', {}, value));
}

function panelContent(monitor, state) {
  const { status } = monitor;
  const rows = [detailRow(t('State'), state.label)];
  if (status && monitor.connection !== 'offline') {
    const { ocr = {}, queue = {} } = status;
    const waiting = t('{queued} waiting, {processing} in progress', {
      queued: formatNumber(queue.queued ?? 0),
      processing: formatNumber(queue.processing ?? 0),
    });
    rows.push(
      detailRow(t('Queue'), waiting),
      detailRow(t('Pages processed'), formatNumber(queue.done ?? 0)),
      queue.error > 0 && detailRow(t('Failed'), tn('{count} page', '{count} pages', queue.error)),
      detailRow(t('Backend'), ocr.backend),
      detailRow(t('Graphics card'), ocr.gpu?.name),
      detailRow(t('Graphics memory'), gpuMemory(ocr.gpu)),
      detailRow(t('Last error'), ocr.last_error),
      detailRow(t('Library'), status.library_dir && h('code', { class: 'path' }, status.library_dir)),
      detailRow(t('Version'), status.version),
    );
  }
  return [
    state.description && h('p', { class: 'engine-panel-text' }, state.description),
    h('dl', { class: 'details-list' }, rows),
  ];
}

/** Header badge: engine state + queue size; toggles a details panel. */
export function mountEngineStatus(container, monitor) {
  const label = h('span', { class: 'engine-label' }, t('OCR…'));
  const queue = h('span', { class: 'engine-queue' });
  const button = h(
    'button',
    {
      type: 'button',
      class: 'engine-badge',
      'aria-expanded': 'false',
      'aria-controls': 'engine-panel',
    },
    h('span', { class: 'status-dot', 'aria-hidden': 'true' }),
    label,
    queue,
  );
  const panel = h('div', { id: 'engine-panel', class: 'engine-panel', hidden: true });
  container.replaceChildren(button, panel);

  const setOpen = (open) => {
    panel.hidden = !open;
    button.setAttribute('aria-expanded', String(open));
  };
  button.addEventListener('click', () => setOpen(panel.hidden));
  document.addEventListener('click', (event) => {
    if (!panel.hidden && !container.contains(event.target)) setOpen(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !panel.hidden) {
      setOpen(false);
      button.focus();
    }
  });

  const render = () => {
    const state = displayedState(monitor);
    const pending = monitor.connection === 'offline' ? null : monitor.pendingPages;
    button.dataset.tone = state.tone;
    label.textContent = state.label;
    queue.textContent = pending ? t('{count} in queue', { count: formatNumber(pending) }) : '';
    queue.hidden = !pending;
    setChildren(panel, panelContent(monitor, state));
  };
  monitor.addEventListener('change', render);
  render();
}

function banner(tone, title, message) {
  return h(
    'div',
    { class: ['banner', `banner-${tone}`], role: 'alert' },
    icon('alert'),
    h('div', {}, h('p', { class: 'banner-title' }, title), message && h('p', {}, message)),
  );
}

function bannerFor(monitor) {
  if (monitor.connection === 'offline') {
    return banner(
      'danger',
      t('The ScanMyLib server is not responding.'),
      t('Retrying every 3 seconds. Check that the PC is on and that the {service} service is running.', {
        service: quoted('api'),
      }),
    );
  }
  const ocr = monitor.status?.ocr;
  if (!ocr) return null;
  if (ocr.reachable === false || ocr.state === 'unreachable') {
    return banner(
      'danger',
      t('The OCR engine is unreachable.'),
      t('Received photos are kept and will be processed as soon as the {container} container responds again.', {
        container: quoted('ocr'),
      }),
    );
  }
  if (ocr.state === 'error') {
    return banner(
      'danger',
      t('The OCR engine could not start.'),
      ocr.last_error ||
        t('Check the logs of the {container} container. The pages stay in the queue.', {
          container: quoted('ocr'),
        }),
    );
  }
  return null;
}

/** Warning banners under the header (server offline, OCR unreachable or failing). */
export function mountBanners(container, monitor) {
  let shownKey = '';
  monitor.addEventListener('change', () => {
    const next = bannerFor(monitor);
    // Re-render only on change, so that screen readers announce a banner once.
    const key = next ? next.textContent : '';
    if (key === shownKey) return;
    shownKey = key;
    setChildren(container, next);
  });
}
