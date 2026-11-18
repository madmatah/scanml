import { BRAND_MARK_HREF, BRAND_MARK_VIEW_BOX } from './brand-mark-drawing.ts';

export function BrandMark({ sizePixels }: { readonly sizePixels: number }) {
  return (
    <svg
      className="brand-mark"
      viewBox={BRAND_MARK_VIEW_BOX}
      width={sizePixels}
      height={sizePixels}
      aria-hidden="true"
      focusable="false"
    >
      <use href={BRAND_MARK_HREF} />
    </svg>
  );
}
