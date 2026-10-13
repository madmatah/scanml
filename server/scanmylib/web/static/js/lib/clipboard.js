/**
 * Copies text to the clipboard; resolves to true on success.
 *
 * The async Clipboard API only exists in secure contexts. On a plain-HTTP LAN
 * origin it is missing, so this falls back to a temporary text area and the
 * (deprecated but still supported) `copy` command.
 */
export async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Permission denied or document not focused: try the fallback below.
    }
  }
  const previousFocus = document.activeElement;
  const area = document.createElement('textarea');
  area.value = text;
  area.setAttribute('readonly', '');
  area.className = 'clipboard-buffer';
  document.body.append(area);
  area.select();
  let copied = false;
  try {
    copied = document.execCommand('copy');
  } catch {
    copied = false;
  }
  area.remove();
  if (previousFocus instanceof HTMLElement) previousFocus.focus();
  return copied;
}
