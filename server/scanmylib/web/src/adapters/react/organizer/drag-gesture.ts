import { inOrder, moveBlock, type PageId, type ReadingOrder } from '../../../domain/reading-order.ts';
import type { DropTarget, PixelPoint } from './grid-geometry.ts';

export const DRAG_THRESHOLD_PIXELS = 5;
export const SCROLL_SLOP_PIXELS = 10;
export const LONG_PRESS_MILLISECONDS = 400;
export const CLICK_AFTER_DRAG_MILLISECONDS = 400;
export const GHOST_MOUSE_OFFSET_PIXELS = 14;
export const GHOST_FINGER_GAP_PIXELS = 28;
// Layout changes smaller than this, such as sub-pixel rounding, are ignored during a drag.
export const LAYOUT_TOLERANCE_PIXELS = 0.5;

const MOUSE = 'mouse';
const MAIN_BUTTON = 0;

export interface Press {
  readonly pointerId: number;
  readonly pointerType: string;
  readonly isPrimary: boolean;
  readonly button: number;
  readonly pointerPixels: PixelPoint;
  readonly pageId: PageId | null;
  readonly isOnHandle: boolean;
  readonly isOnControl: boolean;
}

export interface Gesture {
  readonly pointerId: number;
  readonly pointerType: string;
  readonly pageId: PageId;
  readonly startPixels: PixelPoint;
  readonly pointerPixels: PixelPoint;
  readonly isArmed: boolean;
  readonly isLongPress: boolean;
  readonly isDragging: boolean;
  readonly moving: readonly PageId[];
}

export interface GestureStart {
  readonly gesture: Gesture;
  readonly waitsForLongPress: boolean;
  // A mouse press would otherwise select text or drag the image the browser's way.
  readonly preventsDefault: boolean;
}

export type GestureStep = 'cancel' | 'wait' | 'start' | 'follow';

export type GestureOutcome =
  | { readonly kind: 'drop'; readonly order: ReadingOrder; readonly moving: readonly PageId[] }
  | { readonly kind: 'tap'; readonly pageId: PageId }
  | { readonly kind: 'release' }
  | { readonly kind: 'cancel'; readonly isByKey: boolean };

export interface Release {
  readonly outcome: GestureOutcome;
  readonly ignoresClick: boolean;
}

export interface PixelSize {
  readonly width: number;
  readonly height: number;
}

export interface PixelBox {
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
}

export const isMouse = (pointerType: string): boolean => {
  return pointerType === MOUSE;
};

export const pressGesture = (press: Press, isBlocked: boolean): GestureStart | null => {
  if (isBlocked || !press.isPrimary || press.pageId === null) return null;
  if (isMouse(press.pointerType) && press.button !== MAIN_BUTTON) return null;
  if (!press.isOnHandle && press.isOnControl) return null;
  const mouse = isMouse(press.pointerType);
  return {
    gesture: {
      pointerId: press.pointerId,
      pointerType: press.pointerType,
      pageId: press.pageId,
      startPixels: press.pointerPixels,
      pointerPixels: press.pointerPixels,
      isArmed: mouse || press.isOnHandle,
      isLongPress: false,
      isDragging: false,
      moving: [],
    },
    waitsForLongPress: !mouse && !press.isOnHandle,
    preventsDefault: mouse,
  };
};

export const moveGesture = (
  gesture: Gesture,
  pointerPixels: PixelPoint,
): { readonly gesture: Gesture; readonly step: GestureStep } => {
  const moved = { ...gesture, pointerPixels };
  if (gesture.isDragging) return { gesture: moved, step: 'follow' };
  const distancePixels = Math.hypot(pointerPixels.x - gesture.startPixels.x, pointerPixels.y - gesture.startPixels.y);
  if (!gesture.isArmed) return { gesture: moved, step: distancePixels > SCROLL_SLOP_PIXELS ? 'cancel' : 'wait' };
  if (distancePixels < (gesture.isLongPress ? 1 : DRAG_THRESHOLD_PIXELS)) return { gesture: moved, step: 'wait' };
  return { gesture: moved, step: 'start' };
};

export const pickUpGesture = (gesture: Gesture): Gesture => {
  return gesture.isDragging ? gesture : { ...gesture, isArmed: true, isLongPress: true };
};

export const startDragging = (gesture: Gesture, order: ReadingOrder, selected: ReadonlySet<PageId>): Gesture => {
  const moving = selected.has(gesture.pageId) ? inOrder(order, selected) : [gesture.pageId];
  return { ...gesture, isDragging: true, moving };
};

export const releaseGesture = (gesture: Gesture, target: DropTarget | null, order: ReadingOrder): Release => {
  if (gesture.isDragging) {
    const dropped = target === null ? order.slice() : moveBlock(order, gesture.moving, target.index);
    return { outcome: { kind: 'drop', order: dropped, moving: gesture.moving }, ignoresClick: true };
  }
  if (gesture.isLongPress) return { outcome: { kind: 'tap', pageId: gesture.pageId }, ignoresClick: true };
  return { outcome: { kind: 'release' }, ignoresClick: false };
};

export const ghostPosition = (pointerType: string, pointer: PixelPoint, ghostSize: PixelSize): PixelPoint => {
  if (isMouse(pointerType)) {
    return { x: pointer.x + GHOST_MOUSE_OFFSET_PIXELS, y: pointer.y + GHOST_MOUSE_OFFSET_PIXELS };
  }
  return { x: pointer.x - ghostSize.width / 2, y: pointer.y - ghostSize.height - GHOST_FINGER_GAP_PIXELS };
};

export const hasLayoutMoved = (box: PixelBox, origin: PixelBox): boolean => {
  return (['left', 'top', 'width', 'height'] as const).some(
    (side) => Math.abs(box[side] - origin[side]) > LAYOUT_TOLERANCE_PIXELS,
  );
};

export const coveredTopPixels = (
  headerBottomPixels: number,
  toolbarTopPixels: number,
  toolbarBottomPixels: number,
): number => {
  return toolbarTopPixels <= headerBottomPixels + 1
    ? Math.max(headerBottomPixels, toolbarBottomPixels)
    : headerBottomPixels;
};
