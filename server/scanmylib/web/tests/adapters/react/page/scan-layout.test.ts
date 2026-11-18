import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { layScan, type ScanLayout, scanHeightLimitPixels } from '../../../../src/adapters/react/page/scan-layout.ts';

const PORTRAIT_PIXELS = { width: 800, height: 1200 };

describe('The scan layout', () => {
  describe('The layScan() function', () => {
    describe('When the whole page fits the screen', () => {
      let layout: ScanLayout | null;
      beforeEach(() => {
        layout = layScan({
          imagePixels: PORTRAIT_PIXELS,
          rotationDegrees: 0,
          paneWidthPixels: 600,
          heightLimitPixels: 600,
        });
      });

      it('should scale the scan to the height of the screen, centered and upright', () => {
        assert.deepEqual(layout, {
          framePixels: { width: 400, height: 600 },
          imagePixels: { width: 400, height: 600 },
          transform: 'translate(-50%, -50%) rotate(0deg)',
        });
      });
    });

    describe('When the scan takes the width of the pane', () => {
      let layout: ScanLayout | null;
      beforeEach(() => {
        layout = layScan({
          imagePixels: PORTRAIT_PIXELS,
          rotationDegrees: 0,
          paneWidthPixels: 600,
          heightLimitPixels: null,
        });
      });

      it('should scale it to the width, however tall it gets', () => {
        assert.deepEqual(layout?.framePixels, { width: 600, height: 900 });
      });
    });

    describe('When the page is turned a quarter', () => {
      let layout: ScanLayout | null;
      beforeEach(() => {
        layout = layScan({
          imagePixels: PORTRAIT_PIXELS,
          rotationDegrees: 90,
          paneWidthPixels: 600,
          heightLimitPixels: null,
        });
      });

      it('should give the frame the turned shape, and the image its own shape turned in it', () => {
        assert.deepEqual(layout, {
          framePixels: { width: 600, height: 400 },
          imagePixels: { width: 400, height: 600 },
          transform: 'translate(-50%, -50%) rotate(90deg)',
        });
      });
    });

    describe('When the image is not decoded yet', () => {
      let layout: ScanLayout | null;
      beforeEach(() => {
        layout = layScan({
          imagePixels: { width: 0, height: 0 },
          rotationDegrees: 0,
          paneWidthPixels: 600,
          heightLimitPixels: 600,
        });
      });

      it('should lay out nothing, since its size is not known', () => {
        assert.equal(layout, null);
      });
    });
  });

  describe('The scanHeightLimitPixels() function', () => {
    describe('When the window is tall', () => {
      let heightLimitPixels: number;
      beforeEach(() => {
        heightLimitPixels = scanHeightLimitPixels(900, 56);
      });

      it('should keep room for the header and a margin', () => {
        assert.equal(heightLimitPixels, 732);
      });
    });

    describe('When the window is short', () => {
      let heightLimitPixels: number;
      beforeEach(() => {
        heightLimitPixels = scanHeightLimitPixels(300, 56);
      });

      it('should keep a height where the scan can still be read', () => {
        assert.equal(heightLimitPixels, 240);
      });
    });
  });
});
