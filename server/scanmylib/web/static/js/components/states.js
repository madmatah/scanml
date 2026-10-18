/** Loading, error and empty states shared by the screens. */
import { h } from '../lib/dom.js';
import { t } from '../lib/i18n.js';
import { icon } from './icons.js';

export function loadingState(message = t('Loading…')) {
  return h(
    'div',
    { class: 'state state-loading', role: 'status' },
    h('span', { class: 'spinner', 'aria-hidden': 'true' }),
    h('span', {}, message),
  );
}

/** Error panel with an optional "Retry" button and extra actions. */
export function errorState({ title = t('Could not load'), message, onRetry, actions = [] }) {
  return h(
    'div',
    { class: 'state state-error', role: 'alert' },
    h('span', { class: 'state-icon' }, icon('alert')),
    h('h2', { class: 'state-title' }, title),
    message && h('p', { class: 'state-text' }, message),
    h(
      'div',
      { class: 'state-actions' },
      onRetry && h('button', { type: 'button', class: 'btn', onClick: onRetry }, icon('refresh'), t('Retry')),
      actions,
    ),
  );
}

export function emptyState({ iconName, title, message, actions = [] }) {
  return h(
    'div',
    { class: 'state state-empty' },
    iconName && h('span', { class: 'state-icon' }, icon(iconName)),
    h('h2', { class: 'state-title' }, title),
    message && h('p', { class: 'state-text' }, message),
    actions.length > 0 && h('div', { class: 'state-actions' }, actions),
  );
}
