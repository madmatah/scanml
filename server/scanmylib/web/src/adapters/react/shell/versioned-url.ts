// A browser reuses an image already loaded in the page for the same address without asking again, so an image that
// the api regenerates in place, such as a cover after a rotation, needs an address that changes with it.
export const versionedUrl = (url: string, version: string): string => {
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}v=${encodeURIComponent(version)}`;
};
