import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import {
  coveredTopPixels,
  DRAG_THRESHOLD_PIXELS,
  type Gesture,
  type GestureStart,
  type GestureStep,
  ghostPosition,
  hasLayoutMoved,
  moveGesture,
  type Press,
  pickUpGesture,
  pressGesture,
  type Release,
  releaseGesture,
  SCROLL_SLOP_PIXELS,
  startDragging,
} from '../../../../src/adapters/react/organizer/drag-gesture.ts';
import type { PixelPoint } from '../../../../src/adapters/react/organizer/grid-geometry.ts';

const ORDER = ['a', 'b', 'c', 'd', 'e'];
const START_PIXELS: PixelPoint = { x: 100, y: 200 };
const SECONDARY_BUTTON = 2;

function press(changes: Partial<Press> = {}): Press {
  return {
    pointerId: 1,
    pointerType: 'mouse',
    isPrimary: true,
    button: 0,
    pointerPixels: START_PIXELS,
    pageId: 'c',
    isOnHandle: false,
    isOnControl: false,
    ...changes,
  };
}

function gesture(changes: Partial<Gesture> = {}): Gesture {
  return {
    pointerId: 1,
    pointerType: 'mouse',
    pageId: 'c',
    startPixels: START_PIXELS,
    pointerPixels: START_PIXELS,
    isArmed: true,
    isLongPress: false,
    isDragging: false,
    moving: [],
    ...changes,
  };
}

function stepAfter(moved: Gesture, distancePixels: number): GestureStep {
  return moveGesture(moved, { x: START_PIXELS.x + distancePixels, y: START_PIXELS.y }).step;
}

describe('The drag gesture', () => {
  describe('The pressGesture() function', () => {
    describe('When a mouse presses a card with its main button', () => {
      let start: GestureStart | null;
      beforeEach(() => {
        start = pressGesture(press(), false);
      });

      it('should arm a drag at once, without a long press', () => {
        assert.deepEqual(
          { isArmed: start?.gesture.isArmed, waitsForLongPress: start?.waitsForLongPress },
          { isArmed: true, waitsForLongPress: false },
        );
      });

      it('should keep the browser from selecting text or dragging the image its way', () => {
        assert.equal(start?.preventsDefault, true);
      });
    });

    describe('When a finger presses the body of a card', () => {
      let start: GestureStart | null;
      beforeEach(() => {
        start = pressGesture(press({ pointerType: 'touch' }), false);
      });

      it('should wait for a long press before arming a drag, so that the finger can scroll the page', () => {
        assert.deepEqual(
          { isArmed: start?.gesture.isArmed, waitsForLongPress: start?.waitsForLongPress },
          { isArmed: false, waitsForLongPress: true },
        );
      });

      it('should leave the browser its default, which scrolls', () => {
        assert.equal(start?.preventsDefault, false);
      });
    });

    describe('When a finger presses the grip handle', () => {
      let start: GestureStart | null;
      beforeEach(() => {
        start = pressGesture(press({ pointerType: 'touch', isOnHandle: true, isOnControl: true }), false);
      });

      it('should arm a drag at once', () => {
        assert.deepEqual(
          { isArmed: start?.gesture.isArmed, waitsForLongPress: start?.waitsForLongPress },
          { isArmed: true, waitsForLongPress: false },
        );
      });
    });

    describe('When a press starts no gesture', () => {
      const rows: { situation: string; refused: Press; isBlocked: boolean }[] = [
        { situation: 'a secondary mouse button', refused: press({ button: SECONDARY_BUTTON }), isBlocked: false },
        { situation: 'a checkbox, its label or a button', refused: press({ isOnControl: true }), isBlocked: false },
        { situation: 'a press outside the cards', refused: press({ pageId: null }), isBlocked: false },
        { situation: 'a second finger', refused: press({ isPrimary: false }), isBlocked: false },
        { situation: 'a gesture running, or the order being restored', refused: press(), isBlocked: true },
      ];

      for (const { situation, refused, isBlocked } of rows) {
        describe(`When given ${situation}`, () => {
          let start: GestureStart | null;
          beforeEach(() => {
            start = pressGesture(refused, isBlocked);
          });

          it('should start nothing', () => {
            assert.equal(start, null);
          });
        });
      }
    });
  });

  describe('The moveGesture() function', () => {
    describe('When a mouse moves less than the threshold of a drag', () => {
      let step: GestureStep;
      beforeEach(() => {
        step = stepAfter(gesture(), DRAG_THRESHOLD_PIXELS - 1);
      });

      it('should wait, since the press may still be a click', () => {
        assert.equal(step, 'wait');
      });
    });

    describe('When a mouse moves past the threshold of a drag', () => {
      let step: GestureStep;
      beforeEach(() => {
        step = stepAfter(gesture(), DRAG_THRESHOLD_PIXELS);
      });

      it('should start the drag', () => {
        assert.equal(step, 'start');
      });
    });

    describe('When a finger moves before its long press', () => {
      let shortStep: GestureStep;
      let longStep: GestureStep;
      beforeEach(() => {
        const unarmed = gesture({ pointerType: 'touch', isArmed: false });
        shortStep = stepAfter(unarmed, SCROLL_SLOP_PIXELS);
        longStep = stepAfter(unarmed, SCROLL_SLOP_PIXELS + 1);
      });

      it('should wait while it trembles, and give up once it scrolls the page', () => {
        assert.deepEqual({ shortStep, longStep }, { shortStep: 'wait', longStep: 'cancel' });
      });
    });

    describe('When a finger moves after its long press', () => {
      let step: GestureStep;
      beforeEach(() => {
        step = stepAfter(gesture({ pointerType: 'touch', isArmed: true, isLongPress: true }), 1);
      });

      it('should start the drag at its first move, since the card is already picked up', () => {
        assert.equal(step, 'start');
      });
    });

    describe('When the pointer moves during a drag', () => {
      let moved: { readonly gesture: Gesture; readonly step: GestureStep };
      const pointer = { x: 300, y: 50 };
      beforeEach(() => {
        moved = moveGesture(gesture({ isDragging: true }), pointer);
      });

      it('should follow it', () => {
        assert.deepEqual(
          { step: moved.step, pointerPixels: moved.gesture.pointerPixels },
          { step: 'follow', pointerPixels: pointer },
        );
      });
    });
  });

  describe('The pickUpGesture() function', () => {
    describe('When a finger holds a card still', () => {
      let pickedUp: Gesture;
      beforeEach(() => {
        pickedUp = pickUpGesture(gesture({ pointerType: 'touch', isArmed: false }));
      });

      it('should arm the drag as a long press', () => {
        assert.deepEqual(
          { isArmed: pickedUp.isArmed, isLongPress: pickedUp.isLongPress },
          {
            isArmed: true,
            isLongPress: true,
          },
        );
      });
    });

    describe('When the drag already started', () => {
      let dragging: Gesture;
      let pickedUp: Gesture;
      beforeEach(() => {
        dragging = gesture({ pointerType: 'touch', isDragging: true });
        pickedUp = pickUpGesture(dragging);
      });

      it('should change nothing', () => {
        assert.equal(pickedUp, dragging);
      });
    });
  });

  describe('The startDragging() function', () => {
    describe('When the dragged card is selected', () => {
      let dragging: Gesture;
      beforeEach(() => {
        dragging = startDragging(gesture({ pageId: 'c' }), ORDER, new Set(['e', 'c', 'a']));
      });

      it('should carry the whole selection along, in reading order', () => {
        assert.deepEqual(dragging.moving, ['a', 'c', 'e']);
      });
    });

    describe('When the dragged card is not selected', () => {
      let dragging: Gesture;
      beforeEach(() => {
        dragging = startDragging(gesture({ pageId: 'b' }), ORDER, new Set(['e', 'c']));
      });

      it('should move it alone', () => {
        assert.deepEqual(dragging.moving, ['b']);
      });
    });
  });

  describe('The releaseGesture() function', () => {
    describe('When a drag is dropped on a place', () => {
      let release: Release;
      beforeEach(() => {
        const dragging = gesture({ isDragging: true, moving: ['a', 'c'] });
        release = releaseGesture(dragging, { index: 5, card: 4, side: 'after' }, ORDER);
      });

      it('should drop the moving pages there, and ignore the click that follows', () => {
        assert.deepEqual(release, {
          outcome: { kind: 'drop', order: ['b', 'd', 'e', 'a', 'c'], moving: ['a', 'c'] },
          ignoresClick: true,
        });
      });
    });

    describe('When a drag is dropped away from the cards', () => {
      let release: Release;
      beforeEach(() => {
        release = releaseGesture(gesture({ isDragging: true, moving: ['c'] }), null, ORDER);
      });

      it('should keep the order', () => {
        assert.deepEqual(release.outcome, { kind: 'drop', order: ORDER, moving: ['c'] });
      });
    });

    describe('When a finger lets go of a card it held still', () => {
      let release: Release;
      beforeEach(() => {
        release = releaseGesture(gesture({ pointerType: 'touch', isLongPress: true }), null, ORDER);
      });

      it('should tap the card, and ignore the late click', () => {
        assert.deepEqual(release, { outcome: { kind: 'tap', pageId: 'c' }, ignoresClick: true });
      });
    });

    describe('When a mouse is released without moving', () => {
      let release: Release;
      beforeEach(() => {
        release = releaseGesture(gesture(), null, ORDER);
      });

      it('should leave the selection to the click that follows', () => {
        assert.deepEqual(release, { outcome: { kind: 'release' }, ignoresClick: false });
      });
    });
  });

  describe('The ghostPosition() function', () => {
    const pointer = { x: 400, y: 300 };
    const ghostSize = { width: 72, height: 96 };

    describe('When a mouse drags', () => {
      let position: PixelPoint;
      beforeEach(() => {
        position = ghostPosition('mouse', pointer, ghostSize);
      });

      it('should draw the thumbnail below and right of the pointer', () => {
        assert.deepEqual(position, { x: 414, y: 314 });
      });
    });

    describe('When a finger drags', () => {
      let position: PixelPoint;
      beforeEach(() => {
        position = ghostPosition('touch', pointer, ghostSize);
      });

      it('should draw the thumbnail centered above the finger, so that the finger hides none of it', () => {
        assert.deepEqual(position, { x: 364, y: 176 });
      });
    });
  });

  describe('The hasLayoutMoved() function', () => {
    const origin = { left: 10, top: 300, width: 800, height: 1200 };

    describe('When the lists moved by a rounding', () => {
      let hasMoved: boolean;
      beforeEach(() => {
        hasMoved = hasLayoutMoved({ ...origin, top: 300.4 }, origin);
      });

      it('should say no, so that the cards are not measured again for nothing', () => {
        assert.equal(hasMoved, false);
      });
    });

    describe('When the lists grew', () => {
      let hasMoved: boolean;
      beforeEach(() => {
        hasMoved = hasLayoutMoved({ ...origin, height: 1400 }, origin);
      });

      it('should say yes', () => {
        assert.equal(hasMoved, true);
      });
    });
  });

  describe('The coveredTopPixels() function', () => {
    const headerBottomPixels = 64;

    describe('When the toolbar sticks under the header', () => {
      let coveredTop: number;
      beforeEach(() => {
        coveredTop = coveredTopPixels(headerBottomPixels, 64, 130);
      });

      it('should end at the bottom of the toolbar', () => {
        assert.equal(coveredTop, 130);
      });
    });

    describe('When the toolbar is lower in the page', () => {
      let coveredTop: number;
      beforeEach(() => {
        coveredTop = coveredTopPixels(headerBottomPixels, 400, 466);
      });

      it('should end at the bottom of the header', () => {
        assert.equal(coveredTop, headerBottomPixels);
      });
    });
  });
});
