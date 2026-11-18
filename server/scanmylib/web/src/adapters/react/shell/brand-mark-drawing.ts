// An SVG image could follow the page's theme only through a <style> of its own, which the Content Security Policy
// sent with the file refuses in Firefox (https://lists.w3.org/Archives/Public/public-webappsec/2014Apr/0019.html,
// https://forge.typo3.org/issues/93884): the page draws icon.svg's own mark instead, in the color it inherits.
export const BRAND_MARK_VIEW_BOX = '30 30 48 48';
export const BRAND_MARK_HREF = '/static/icons/icon.svg#mark';
