export interface AddressBar {
  readonly location: { readonly hash: string; readonly pathname: string; readonly search: string };
  readonly history: { replaceState(data: null, unused: string, url: string): void };
  addEventListener(type: 'popstate' | 'hashchange', listener: () => void): void;
}

const SIGN_IN_LINK = /^#token=([^&]*)/;
const HOME_FRAGMENT = '#/';

// The token of a sign-in link (#token=…) is a secret: it leaves the address bar and the history entry before anything
// else reads them, the router included. The fragment never reaches the server.
export const takeSignInToken = (addressBar: AddressBar): string | null => {
  const { hash, pathname, search } = addressBar.location;
  const match = SIGN_IN_LINK.exec(hash);
  if (match === null) return null;
  addressBar.history.replaceState(null, '', `${pathname}${search}${HOME_FRAGMENT}`);
  try {
    return decodeURIComponent(match[1] ?? '').trim() || null;
  } catch {
    return null;
  }
};

// Listeners of one target run in the order they were added: watching before the router is created strips the token
// before the router's own listener reads the address.
export const watchSignInLinks = (addressBar: AddressBar, signInWithLink: (token: string) => void): void => {
  const takeToken = () => {
    const token = takeSignInToken(addressBar);
    if (token !== null) signInWithLink(token);
  };
  addressBar.addEventListener('popstate', takeToken);
  addressBar.addEventListener('hashchange', takeToken);
};
