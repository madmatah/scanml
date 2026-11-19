import type { Scheduler } from '../../../application/scheduler.ts';

export type ToastTone = 'info' | 'success' | 'error';

export interface Toast {
  readonly id: number;
  readonly message: string;
  readonly tone: ToastTone;
}

export interface Toasts {
  subscribe(listener: () => void): () => void;
  getSnapshot(): readonly Toast[];
  show(message: string, tone: ToastTone): void;
  dismiss(id: number): void;
}

export const TOAST_DURATION_MILLISECONDS: Readonly<Record<ToastTone, number>> = {
  info: 4000,
  success: 4000,
  error: 9000,
};
export const MOST_TOASTS_SHOWN = 3;

export const createToasts = (scheduler: Scheduler): Toasts => {
  let shown: readonly Toast[] = [];
  let lastId = 0;
  const listeners = new Set<() => void>();

  const replace = (next: readonly Toast[]): void => {
    shown = next;
    for (const listener of listeners) listener();
  };

  const dismiss = (id: number): void => {
    if (shown.some((toast) => toast.id === id)) replace(shown.filter((toast) => toast.id !== id));
  };

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    getSnapshot: () => shown,
    show(message, tone) {
      lastId += 1;
      const toast: Toast = { id: lastId, message, tone };
      const kept = shown.slice(Math.max(0, shown.length - (MOST_TOASTS_SHOWN - 1)));
      replace([...kept, toast]);
      scheduler.schedule(() => dismiss(toast.id), TOAST_DURATION_MILLISECONDS[tone]);
    },
    dismiss,
  };
};
