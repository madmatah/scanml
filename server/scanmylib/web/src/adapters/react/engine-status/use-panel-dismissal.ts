import { type RefObject, useEffect, useRef } from 'react';

export interface PanelDismissal {
  readonly container: RefObject<HTMLDivElement | null>;
  readonly badge: RefObject<HTMLButtonElement | null>;
}

export const usePanelDismissal = (isOpen: boolean, onClose: () => void): PanelDismissal => {
  const container = useRef<HTMLDivElement>(null);
  const badge = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const closeOnClickOutside = (event: MouseEvent): void => {
      if (event.target instanceof Node && container.current?.contains(event.target)) return;
      onClose();
    };
    const closeOnEscape = (event: KeyboardEvent): void => {
      if (event.key !== 'Escape') return;
      onClose();
      badge.current?.focus();
    };
    document.addEventListener('click', closeOnClickOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('click', closeOnClickOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [isOpen, onClose]);

  return { container, badge };
};
