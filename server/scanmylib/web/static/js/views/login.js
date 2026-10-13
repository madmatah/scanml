/** Sign-in screen: exchanges the access token for the session cookie. */
import { ApiError } from '../api.js';
import { icon } from '../components/icons.js';
import { h } from '../lib/dom.js';
import { errorMessage } from '../lib/errors.js';
import { t, tc, tNodes } from '../lib/i18n.js';
import { signIn } from '../session.js';

/**
 * @param {HTMLElement} root
 * @param {{ setTitle: Function, onSignedIn: Function, message?: string }} context
 *   `message` explains why the user lands here (expired session, bad link…).
 */
export function mountLogin(root, { setTitle, onSignedIn, message }) {
  setTitle(tc('screen title', 'Sign in'));

  const token = h('input', {
    id: 'login-token', name: 'token', type: 'password', class: 'input input-mono', required: true,
    autocomplete: 'current-password', autocapitalize: 'none', spellcheck: 'false', 'aria-describedby': 'login-help',
  });
  const reveal = h('button', {
    type: 'button', class: 'btn btn-icon', 'aria-pressed': 'false', 'aria-label': t('Show token'),
  }, icon('eye'));
  const error = h('p', { class: 'form-error', role: 'alert', hidden: !message }, message ?? '');
  const submit = h('button', { type: 'submit', class: 'btn btn-primary btn-block' }, t('Sign in'));

  const form = h('form', { class: 'card login-card', novalidate: true },
    h('div', { class: 'login-brand' },
      h('img', { src: '/static/icons/icon.svg', alt: '', width: 48, height: 48 }),
      h('div', {},
        h('h1', { tabindex: '-1' }, 'ScanMyLib'),
        h('p', { class: 'muted' }, t('Your digitized library')))),
    // Lets password managers store the token under a recognizable name.
    h('input', {
      type: 'text', name: 'username', autocomplete: 'username', value: 'ScanMyLib', hidden: true, readonly: true,
    }),
    h('div', { class: 'field' },
      h('label', { for: token.id }, t('Access token')),
      h('div', { class: 'input-group' }, token, reveal),
      h('p', { id: 'login-help', class: 'hint' },
        tNodes('The server creates this token the first time it starts, in the file {file} of its data folder. '
          + 'A link of the form {link} signs you in directly.', {
          file: h('code', {}, 'state/token'),
          link: h('code', {}, 'http://…/#token=…'),
        }))),
    error,
    submit);

  reveal.addEventListener('click', () => {
    const visible = token.type === 'password';
    token.type = visible ? 'text' : 'password';
    reveal.setAttribute('aria-pressed', String(visible));
    reveal.setAttribute('aria-label', visible ? t('Hide token') : t('Show token'));
    reveal.replaceChildren(icon(visible ? 'eye-off' : 'eye'));
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const value = token.value.trim();
    if (!value) {
      error.textContent = t('Enter the access token.');
      error.hidden = false;
      token.focus();
      return;
    }
    submit.disabled = true;
    submit.textContent = t('Signing in…');
    try {
      await signIn(value);
      onSignedIn();
    } catch (failure) {
      error.textContent = failure instanceof ApiError && failure.status === 401
        ? t('Invalid token. Check it and try again.')
        : errorMessage(failure, t('Could not sign in.'));
      error.hidden = false;
      token.select();
    } finally {
      submit.disabled = false;
      submit.textContent = t('Sign in');
    }
  });

  root.replaceChildren(h('section', { class: 'view login' }, form));
  token.focus();
}
