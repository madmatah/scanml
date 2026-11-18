import type { Clipboard } from '../../application/clipboard.ts';

export interface ClipboardApis {
  readonly isSecureContext: boolean;
  readonly writeText: ((text: string) => Promise<void>) | null;
  readonly copyWithCommand: (text: string) => boolean;
}

// The asynchronous Clipboard API exists only in a secure context, and the web UI is usually opened over plain HTTP on
// the local network: there, the text is copied from a temporary text area by the copy command, deprecated but still
// supported.
export function createClipboard(apis: ClipboardApis): Clipboard {
  return {
    async copyText(text) {
      if (apis.isSecureContext && apis.writeText !== null) {
        try {
          await apis.writeText(text);
          return true;
        } catch {
          // Refused, or the page lost the focus: the copy command may still succeed.
        }
      }
      return apis.copyWithCommand(text);
    },
  };
}
