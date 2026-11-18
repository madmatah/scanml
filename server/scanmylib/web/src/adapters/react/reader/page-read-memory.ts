// The page being read is kept in the screen's own history entry, for "Back" and a reload of the browser. The entry also
// holds the router's own state, which is kept as it is.
const PAGE_READ_FIELD = 'readingPage';

function isRecord(state: unknown): state is { readonly [field: string]: unknown } {
  return typeof state === 'object' && state !== null && !Array.isArray(state);
}

export function pageReadIn(historyState: unknown): string | null {
  if (!isRecord(historyState)) return null;
  const pageKey = historyState[PAGE_READ_FIELD];
  return typeof pageKey === 'string' ? pageKey : null;
}

export function withPageRead(historyState: unknown, pageKey: string): Record<string, unknown> {
  return { ...(isRecord(historyState) ? historyState : {}), [PAGE_READ_FIELD]: pageKey };
}

// A history entry is the reader's while the address bar shows the reader's path, which the router may have left already
// when the screen has not yet gone.
export function isAddressOf(addressFragment: string, routerPath: string): boolean {
  return addressFragment === `#${routerPath}`;
}
