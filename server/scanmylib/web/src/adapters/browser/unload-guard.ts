export interface LeavingEvent {
  preventDefault(): void;
  returnValue: unknown;
}

export interface LeavingWindow {
  addEventListener(type: 'beforeunload', listener: (event: LeavingEvent) => void): void;
}

export function guardUnload(page: LeavingWindow, isWorking: () => boolean): void {
  page.addEventListener('beforeunload', (event) => {
    if (!isWorking()) return;
    event.preventDefault();
    // Still needed by some browsers to show their question.
    event.returnValue = '';
  });
}
