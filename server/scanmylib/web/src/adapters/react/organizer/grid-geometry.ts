import type { Side } from '../../../domain/reading-order.ts';

export interface PixelPoint {
  readonly x: number;
  readonly y: number;
}

export type PixelRectangle = {
  readonly left: number;
  readonly top: number;
  readonly right: number;
  readonly bottom: number;
};

export type GridRow = {
  readonly first: number;
  readonly last: number;
  readonly top: number;
  readonly bottom: number;
};

export type DropTarget = {
  readonly index: number;
  readonly card: number;
  readonly side: Side;
};

export type InsertionMark = {
  readonly x: number;
  readonly top: number;
  readonly bottom: number;
};

export type ScrollZone = {
  readonly zonePixels?: number;
  readonly maxStepPixels?: number;
};

// Cards whose tops differ by sub-pixel rounding still lie on one row.
const ROW_TOLERANCE_PIXELS = 2;

const followsOnRow = (previous: PixelRectangle, next: PixelRectangle): boolean => {
  return Math.abs(previous.top - next.top) <= ROW_TOLERANCE_PIXELS && next.left > previous.left;
};

export const gridRows = (cards: readonly PixelRectangle[]): GridRow[] => {
  const rows: GridRow[] = [];
  let previous: PixelRectangle | undefined;
  cards.forEach((card, index) => {
    const row = rows.at(-1);
    if (row !== undefined && previous !== undefined && followsOnRow(previous, card)) {
      rows[rows.length - 1] = { ...row, last: index, bottom: Math.max(row.bottom, card.bottom) };
    } else {
      rows.push({ first: index, last: index, top: card.top, bottom: card.bottom });
    }
    previous = card;
  });
  return rows;
};

const cardAt = (cards: readonly PixelRectangle[], index: number): PixelRectangle => {
  const card = cards[index];
  if (card === undefined) throw new RangeError(`No card at index ${index} of ${cards.length}`);
  return card;
};

export const dropTarget = (cards: readonly PixelRectangle[], pointerPixels: PixelPoint): DropTarget | null => {
  let nearestRow: GridRow | null = null;
  let nearestDistance = Infinity;
  for (const row of gridRows(cards)) {
    const distance = Math.max(row.top - pointerPixels.y, pointerPixels.y - row.bottom, 0);
    if (distance < nearestDistance) {
      nearestRow = row;
      nearestDistance = distance;
    }
  }
  if (nearestRow === null) return null;
  for (let index = nearestRow.first; index <= nearestRow.last; index += 1) {
    const card = cardAt(cards, index);
    if (pointerPixels.x < (card.left + card.right) / 2) return { index, card: index, side: 'before' };
  }
  return { index: nearestRow.last + 1, card: nearestRow.last, side: 'after' };
};

export const columnGap = (cards: readonly PixelRectangle[], fallbackPixels = 12): number => {
  for (let index = 1; index < cards.length; index += 1) {
    const previous = cardAt(cards, index - 1);
    const card = cardAt(cards, index);
    if (followsOnRow(previous, card)) return card.left - previous.right;
  }
  return fallbackPixels;
};

export const insertionMark = (
  cards: readonly PixelRectangle[],
  target: DropTarget,
  gapPixels: number,
): InsertionMark => {
  const card = cardAt(cards, target.card);
  let left: number;
  if (target.side === 'before') {
    const previous = cards[target.card - 1];
    left =
      previous !== undefined && followsOnRow(previous, card)
        ? (previous.right + card.left) / 2
        : card.left - gapPixels / 2;
  } else {
    const next = cards[target.card + 1];
    left = next !== undefined && followsOnRow(card, next) ? (card.right + next.left) / 2 : card.right + gapPixels / 2;
  }
  return { x: left, top: card.top, bottom: card.bottom };
};

export const autoScrollStep = (
  pointerTopPixels: number,
  topPixels: number,
  bottomPixels: number,
  { zonePixels = 64, maxStepPixels = 18 }: ScrollZone = {},
): number => {
  if (pointerTopPixels < topPixels + zonePixels) {
    return -Math.ceil(maxStepPixels * Math.min(1, (topPixels + zonePixels - pointerTopPixels) / zonePixels));
  }
  if (pointerTopPixels > bottomPixels - zonePixels) {
    return Math.ceil(maxStepPixels * Math.min(1, (pointerTopPixels - (bottomPixels - zonePixels)) / zonePixels));
  }
  return 0;
};
