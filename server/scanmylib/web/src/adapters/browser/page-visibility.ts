import type { PageVisibility } from '../../application/engine-status.ts';

export interface VisibleDocument {
  readonly hidden: boolean;
  addEventListener(type: 'visibilitychange', listener: () => void): void;
  removeEventListener(type: 'visibilitychange', listener: () => void): void;
}

export const createPageVisibility = (page: VisibleDocument): PageVisibility => {
  return {
    isVisible: () => !page.hidden,
    watch(listener) {
      page.addEventListener('visibilitychange', listener);
      return () => page.removeEventListener('visibilitychange', listener);
    },
  };
};
