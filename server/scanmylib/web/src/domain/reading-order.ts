import type { PageSummary } from './document-details.ts';

export type PageId = string;
export type ReadingOrder = readonly PageId[];
export type Side = 'before' | 'after';

export type Placement =
  | { readonly kind: 'conflict' }
  | { readonly kind: 'unchanged' }
  | { readonly kind: 'moved'; readonly order: ReadingOrder; readonly moved: readonly PageId[] };

export interface ReadingOrderGroups {
  readonly placed: readonly PageId[];
  readonly unplaced: readonly PageId[];
  readonly hasPlacedPages: boolean;
}

export const sameOrder = (first: ReadingOrder, second: ReadingOrder): boolean => {
  return first.length === second.length && first.every((pageId, index) => pageId === second[index]);
};

export const inOrder = (order: ReadingOrder, pageIds: Iterable<PageId>): PageId[] => {
  const wanted = new Set(pageIds);
  return order.filter((pageId) => wanted.has(pageId));
};

export const moveBlock = (order: ReadingOrder, moving: Iterable<PageId>, index: number): PageId[] => {
  const movingSet = new Set(moving);
  const stays = (pageId: PageId): boolean => !movingSet.has(pageId);
  return [
    ...order.slice(0, index).filter(stays),
    ...order.filter((pageId) => movingSet.has(pageId)),
    ...order.slice(index).filter(stays),
  ];
};

export const moveNextTo = (order: ReadingOrder, moving: Iterable<PageId>, targetId: PageId, side: Side): PageId[] => {
  const index = order.indexOf(targetId);
  if (index < 0) return order.slice();
  return moveBlock(order, moving, side === 'after' ? index + 1 : index);
};

export const moveByOne = (order: ReadingOrder, pageId: PageId, step: -1 | 1): PageId[] => {
  const index = order.indexOf(pageId);
  const neighbor = order[index + step];
  if (index < 0 || neighbor === undefined) return order.slice();
  return moveNextTo(order, [pageId], neighbor, step < 0 ? 'before' : 'after');
};

export const rangeOf = (order: ReadingOrder, fromId: PageId | null, toId: PageId): PageId[] => {
  const from = fromId === null ? -1 : order.indexOf(fromId);
  const to = order.indexOf(toId);
  if (to < 0) return [];
  if (from < 0) return [toId];
  return order.slice(Math.min(from, to), Math.max(from, to) + 1);
};

export const spanOf = (order: ReadingOrder, pageIds: Iterable<PageId>): PageId[] => {
  const positions = inOrder(order, pageIds).map((pageId) => order.indexOf(pageId));
  const first = positions[0];
  const last = positions.at(-1);
  if (first === undefined || last === undefined) return [];
  return order.slice(first, last + 1);
};

export const readingOrderGroups = (
  order: ReadingOrder,
  pages: ReadonlyMap<PageId, PageSummary>,
): ReadingOrderGroups => {
  const isUnplaced = (pageId: PageId | undefined): boolean =>
    pageId !== undefined && pages.get(pageId)?.placement === 'unplaced';
  const hasPlacedPages = order.some((pageId) => !isUnplaced(pageId));
  let split = order.length;
  if (hasPlacedPages) while (split > 0 && isUnplaced(order[split - 1])) split -= 1;
  return { placed: order.slice(0, split), unplaced: order.slice(split), hasPlacedPages };
};

export const placeSelection = (
  order: ReadingOrder,
  moving: readonly PageId[],
  targetId: PageId,
  side: Side,
): Placement => {
  const stillMoving = inOrder(order, moving);
  if (!order.includes(targetId) || stillMoving.length !== moving.length) return { kind: 'conflict' };
  const placed = moveNextTo(order, stillMoving, targetId, side);
  if (sameOrder(placed, order)) return { kind: 'unchanged' };
  return { kind: 'moved', order: placed, moved: stillMoving };
};
