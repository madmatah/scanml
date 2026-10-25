// An SVG image could follow the page's theme only through a <style> of its own, which the Content Security Policy
// sent with the file refuses in Firefox (https://lists.w3.org/Archives/Public/public-webappsec/2014Apr/0019.html,
// https://forge.typo3.org/issues/93884): the page draws icon.svg's own mark instead, in the color it inherits.

const SVG_NS = 'http://www.w3.org/2000/svg';

export const BRAND_MARK_VIEW_BOX = '30 30 48 48';
export const BRAND_MARK_HREF = '/static/icons/icon.svg#mark';

export function createBrandMark(sizePixels) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', 'brand-mark');
  svg.setAttribute('viewBox', BRAND_MARK_VIEW_BOX);
  svg.setAttribute('width', String(sizePixels));
  svg.setAttribute('height', String(sizePixels));
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  const use = document.createElementNS(SVG_NS, 'use');
  use.setAttribute('href', BRAND_MARK_HREF);
  svg.append(use);
  return svg;
}
