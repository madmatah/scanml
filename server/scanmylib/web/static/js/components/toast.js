import { h } from '../lib/dom.js';
import { t } from '../lib/i18n.js';
import { icon } from './icons.js';

const DURATION_MS = { info: 4000, success: 4000, error: 9000 };
const MAX_VISIBLE = 3;

/**
 * Shows a short notification at the bottom of the screen. Screen readers
 * announce it (politely, or immediately for errors).
 *
 * @param {string} message
 * @param {{ tone?: 'info' | 'success' | 'error' }} [options]
 */
export function toast(message, { tone = 'info' } = {}) {
  const region = document.getElementById('toasts');
  const close = h('button', { type: 'button', class: 'toast-close', 'aria-label': t('Close notification') }, icon('x'));
  const item = h(
    'div',
    { class: ['toast', `toast-${tone}`], role: tone === 'error' ? 'alert' : 'status' },
    h('p', { class: 'toast-message' }, message),
    close,
  );
  const dismiss = () => item.remove();
  close.addEventListener('click', dismiss);
  while (region.children.length >= MAX_VISIBLE) region.firstElementChild.remove();
  region.append(item);
  setTimeout(dismiss, DURATION_MS[tone] ?? DURATION_MS.info);
}
