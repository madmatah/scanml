import { type RefObject, useCallback, useLayoutEffect, useRef } from 'react';

export function useModal(
  dialog: RefObject<HTMLDialogElement | null>,
  initialFocus: RefObject<HTMLElement | null>,
): () => void {
  const opener = useRef<Element | null>(null);

  useLayoutEffect(() => {
    const element = dialog.current;
    if (element === null || element.open) return;
    opener.current = document.activeElement;
    element.showModal();
    initialFocus.current?.focus();
  }, [dialog, initialFocus]);

  return useCallback(() => {
    const element = opener.current;
    if (element instanceof HTMLElement && element.isConnected) element.focus();
  }, []);
}
