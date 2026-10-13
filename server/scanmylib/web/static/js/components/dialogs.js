/**
 * Modal dialogs built on <dialog>: the browser traps focus and closes them
 * with Escape; focus goes back to the control that opened them.
 */
import { h, uniqueId } from '../lib/dom.js';
import { errorMessage } from '../lib/errors.js';
import { t } from '../lib/i18n.js';
import { documentKinds } from '../lib/labels.js';

/** Shows a <dialog> as a modal; it is removed when closed and focus returns to the opener. */
export function openModal(dialog) {
  const opener = document.activeElement;
  dialog.addEventListener('close', () => {
    dialog.remove();
    if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
  }, { once: true });
  document.body.append(dialog);
  dialog.showModal();
}

/**
 * Asks the user to confirm an action. Resolves to true when confirmed.
 * "Cancel" has the initial focus so that Enter never confirms by accident.
 */
export function confirmDialog({ title, message, confirmLabel, danger = false }) {
  return new Promise((resolve) => {
    const titleId = uniqueId('dialog-title');
    const dialog = h('dialog', { class: 'dialog', 'aria-labelledby': titleId },
      h('form', { method: 'dialog', class: 'dialog-body' },
        h('h2', { id: titleId, class: 'dialog-title' }, title),
        message && h('p', { class: 'dialog-text' }, message),
        h('div', { class: 'dialog-actions' },
          h('button', { type: 'submit', value: 'cancel', class: 'btn', autofocus: true }, t('Cancel')),
          h('button', { type: 'submit', value: 'confirm', class: ['btn', danger ? 'btn-danger-solid' : 'btn-primary'] },
            confirmLabel))));
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), { once: true });
    openModal(dialog);
  });
}

/**
 * Form for a document's metadata, used to create and to edit documents.
 *
 * `onSubmit(values)` is awaited; if it throws, the error is shown and the
 * dialog stays open. Resolves with what `onSubmit` returned, or null when
 * the dialog was canceled.
 */
export function documentDialog({ heading, submitLabel, initial = {}, withNotes = false, onSubmit }) {
  return new Promise((resolve) => {
    const ids = {
      heading: uniqueId('dialog-title'),
      title: uniqueId('doc-title'),
      author: uniqueId('doc-author'),
      notes: uniqueId('doc-notes'),
      unwarpHint: uniqueId('doc-unwarp-hint'),
    };
    const title = h('input', {
      id: ids.title, name: 'title', class: 'input', required: true, maxlength: 300, autocomplete: 'off',
      value: initial.title ?? '',
    });
    const author = h('input', {
      id: ids.author, name: 'author', class: 'input', maxlength: 300, autocomplete: 'off', value: initial.author ?? '',
    });
    const kindChoices = documentKinds().map(([value, label]) => h('label', { class: 'segmented-option' },
      h('input', { type: 'radio', name: 'kind', value, checked: (initial.kind ?? 'book') === value }),
      h('span', {}, label)));
    // New books default to unwarping (curved pages near the binding), other kinds
    // do not; once the user ticks or unticks the box, their choice sticks.
    const creating = initial.unwarp === undefined;
    const unwarp = h('input', {
      type: 'checkbox', name: 'unwarp', 'aria-describedby': ids.unwarpHint,
      checked: creating ? (initial.kind ?? 'book') === 'book' : Boolean(initial.unwarp),
    });
    let unwarpTouched = !creating;
    unwarp.addEventListener('change', () => {
      unwarpTouched = true;
    });
    const notes = withNotes
      ? h('textarea', {
        id: ids.notes, name: 'notes', class: 'input', rows: 3, maxlength: 20000, value: initial.notes ?? '',
      })
      : null;
    const error = h('p', { class: 'form-error', role: 'alert', hidden: true });
    const submit = h('button', { type: 'submit', class: 'btn btn-primary' }, submitLabel);
    const cancel = h('button', { type: 'button', class: 'btn' }, t('Cancel'));

    const form = h('form', { class: 'dialog-body', novalidate: true },
      h('h2', { id: ids.heading, class: 'dialog-title' }, heading),
      h('div', { class: 'field' }, h('label', { for: ids.title }, t('Title')), title),
      h('div', { class: 'field' },
        h('label', { for: ids.author }, t('Author'), ' ', h('span', { class: 'optional' }, t('(optional)'))),
        author),
      h('fieldset', { class: 'field' },
        h('legend', {}, t('Type')),
        h('div', { class: 'segmented' }, kindChoices)),
      h('label', { class: 'checkbox' },
        unwarp,
        h('span', {},
          h('span', { class: 'checkbox-label' }, t('Bound book: straighten curved pages')),
          h('span', { id: ids.unwarpHint, class: 'hint' },
            t('Flattens the curvature of the pages near the binding before OCR (a little slower).')))),
      notes && h('div', { class: 'field' },
        h('label', { for: ids.notes }, t('Notes'), ' ', h('span', { class: 'optional' }, t('(optional)'))),
        notes),
      error,
      h('div', { class: 'dialog-actions' }, cancel, submit));

    const dialog = h('dialog', { class: 'dialog', 'aria-labelledby': ids.heading }, form);
    let result = null;
    let busy = false;

    const showError = (message) => {
      error.textContent = message;
      error.hidden = false;
    };
    // aria-disabled rather than disabled, so that the focused button keeps the focus.
    const setBusy = (value) => {
      busy = value;
      for (const button of [submit, cancel]) {
        if (value) button.setAttribute('aria-disabled', 'true');
        else button.removeAttribute('aria-disabled');
      }
    };

    cancel.addEventListener('click', () => {
      if (!busy) dialog.close();
    });
    title.addEventListener('input', () => {
      error.hidden = true;
    });
    form.addEventListener('change', (event) => {
      if (event.target.name === 'kind' && !unwarpTouched) unwarp.checked = event.target.value === 'book';
    });
    // Escape must not drop a request that is being sent.
    dialog.addEventListener('cancel', (event) => {
      if (busy) event.preventDefault();
    });
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (busy) return;
      const values = {
        title: title.value.trim(),
        author: author.value.trim(),
        kind: form.elements.kind.value,
        unwarp: unwarp.checked,
      };
      if (notes) values.notes = notes.value.trim();
      if (!values.title) {
        showError(t('The title is required.'));
        title.focus();
        return;
      }
      setBusy(true);
      error.hidden = true;
      try {
        result = await onSubmit(values);
        dialog.close();
      } catch (failure) {
        showError(errorMessage(failure, t('Could not save.')));
      } finally {
        setBusy(false);
      }
    });
    dialog.addEventListener('close', () => resolve(result), { once: true });
    openModal(dialog);
    title.focus();
  });
}
