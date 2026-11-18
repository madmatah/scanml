import type { Clipboard } from '../../application/clipboard.ts';
import { createClipboard } from './clipboard.ts';

function copyWithTextArea(page: Document, text: string): boolean {
  const previousFocus = page.activeElement;
  const area = page.createElement('textarea');
  area.value = text;
  area.setAttribute('readonly', '');
  area.className = 'clipboard-buffer';
  page.body.append(area);
  area.select();
  let isCopied: boolean;
  try {
    isCopied = page.execCommand('copy');
  } catch {
    isCopied = false;
  }
  area.remove();
  if (previousFocus instanceof HTMLElement) previousFocus.focus();
  return isCopied;
}

export function createWindowClipboard(browser: Window): Clipboard {
  const { clipboard } = browser.navigator;
  return createClipboard({
    isSecureContext: browser.isSecureContext,
    // Undefined outside a secure context, whatever the types of the DOM say.
    writeText: clipboard === undefined ? null : (text) => clipboard.writeText(text),
    copyWithCommand: (text) => copyWithTextArea(browser.document, text),
  });
}
