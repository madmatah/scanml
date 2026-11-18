import { type PageId, type ReadingOrder, rangeOf, spanOf } from './reading-order.ts';

export interface Selection {
  readonly selected: ReadonlySet<PageId>;
  readonly anchor: PageId | null;
}

export interface SelectionKeys {
  readonly isToggle: boolean;
  readonly isRange: boolean;
}

export const NO_SELECTION: Selection = { selected: new Set(), anchor: null };

export function selectPage(selection: Selection, order: ReadingOrder, pageId: PageId, keys: SelectionKeys): Selection {
  const { selected, anchor } = selection;
  if (keys.isRange && anchor !== null) {
    const range = rangeOf(order, anchor, pageId);
    return { selected: new Set(keys.isToggle ? [...selected, ...range] : range), anchor };
  }
  if (keys.isToggle) {
    const toggled = new Set(selected);
    if (toggled.has(pageId)) toggled.delete(pageId);
    else toggled.add(pageId);
    return { selected: toggled, anchor: pageId };
  }
  return { selected: new Set([pageId]), anchor: pageId };
}

export function selectSpan(selection: Selection, order: ReadingOrder): Selection {
  return { ...selection, selected: new Set(spanOf(order, selection.selected)) };
}

export function keepShownPages(selection: Selection, order: ReadingOrder): Selection {
  const shown = new Set(order);
  return {
    selected: new Set([...selection.selected].filter((pageId) => shown.has(pageId))),
    anchor: selection.anchor !== null && shown.has(selection.anchor) ? selection.anchor : null,
  };
}
