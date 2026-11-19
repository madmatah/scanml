import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { type AddressBar, takeSignInToken, watchSignInLinks } from './address-bar.ts';

interface StubAddressBar extends AddressBar {
  readonly replacedUrls: string[];
  navigate(hash: string): void;
  dispatch(type: 'popstate' | 'hashchange'): void;
}

function createAddressBar(hash: string, pathname = '/', search = ''): StubAddressBar {
  const location = { hash, pathname, search };
  const replacedUrls: string[] = [];
  const target = new EventTarget();
  return {
    location,
    replacedUrls,
    history: {
      replaceState(_data, _unused, url) {
        replacedUrls.push(url);
        location.hash = url.slice(url.indexOf('#'));
      },
    },
    addEventListener: (type, listener) => target.addEventListener(type, listener),
    navigate(nextHash) {
      location.hash = nextHash;
    },
    dispatch: (type) => target.dispatchEvent(new Event(type)),
  };
}

describe('The address bar', () => {
  describe('The takeSignInToken() function', () => {
    const tokens = [
      {
        situation: 'When the address holds a sign-in link',
        hash: '#token=a-token',
        rule: 'should give its token',
        expectedToken: 'a-token',
      },
      {
        situation: 'When the token of the link is escaped and padded',
        hash: '#token=%20a%2Btoken%20',
        rule: 'should give it unescaped and trimmed',
        expectedToken: 'a+token',
      },
      {
        situation: 'When the token of the link is followed by other parameters',
        hash: '#token=a-token&lang=fr',
        rule: 'should give the token alone',
        expectedToken: 'a-token',
      },
      {
        situation: 'When the token of the link holds a malformed escape',
        hash: '#token=a%E0%A4%A',
        rule: 'should give no token',
        expectedToken: null,
      },
      {
        situation: 'When the token of the link is empty',
        hash: '#token=%20',
        rule: 'should give no token',
        expectedToken: null,
      },
    ];

    for (const { situation, hash, rule, expectedToken } of tokens) {
      describe(situation, () => {
        let addressBar: StubAddressBar;
        let token: string | null;
        beforeEach(() => {
          addressBar = createAddressBar(hash);
          token = takeSignInToken(addressBar);
        });

        it(rule, () => {
          assert.equal(token, expectedToken);
        });

        it('should replace the history entry with the home of the UI, so that the secret leaves the address', () => {
          assert.deepEqual(addressBar.replacedUrls, ['/#/']);
        });
      });
    }

    describe('When the page has a path and a query', () => {
      let addressBar: StubAddressBar;
      beforeEach(() => {
        addressBar = createAddressBar('#token=a-token', '/app/', '?source=qr');
        takeSignInToken(addressBar);
      });

      it('should keep them in the history entry it replaces', () => {
        assert.deepEqual(addressBar.replacedUrls, ['/app/?source=qr#/']);
      });
    });

    describe('When the address holds no sign-in link', () => {
      let addressBar: StubAddressBar;
      let token: string | null;
      beforeEach(() => {
        addressBar = createAddressBar('#/login');
        token = takeSignInToken(addressBar);
      });

      it('should give no token', () => {
        assert.equal(token, null);
      });

      it('should leave the history entry as it is', () => {
        assert.deepEqual(addressBar.replacedUrls, []);
      });
    });
  });

  describe('The watchSignInLinks() function', () => {
    const navigations = ['popstate', 'hashchange'] as const;

    for (const navigation of navigations) {
      describe(`When a sign-in link is opened while the UI runs, and the browser dispatches ${navigation}`, () => {
        let tokens: string[];
        let addressReadAfter: string;
        beforeEach(() => {
          tokens = [];
          const addressBar = createAddressBar('#/');
          watchSignInLinks(addressBar, (token) => tokens.push(token));
          addressBar.addEventListener(navigation, () => {
            addressReadAfter = addressBar.location.hash;
          });
          addressBar.navigate('#token=a-token');
          addressBar.dispatch(navigation);
        });

        it('should sign in with its token', () => {
          assert.deepEqual(tokens, ['a-token']);
        });

        it('should strip the token before a listener added later reads the address, as the router does', () => {
          assert.equal(addressReadAfter, '#/');
        });
      });
    }

    describe('When the browser dispatches both events for one sign-in link', () => {
      let tokens: string[];
      beforeEach(() => {
        tokens = [];
        const addressBar = createAddressBar('#/');
        watchSignInLinks(addressBar, (token) => tokens.push(token));
        addressBar.navigate('#token=a-token');
        addressBar.dispatch('popstate');
        addressBar.dispatch('hashchange');
      });

      it('should sign in once', () => {
        assert.deepEqual(tokens, ['a-token']);
      });
    });

    describe('When the UI navigates to one of its screens', () => {
      let tokens: string[];
      beforeEach(() => {
        tokens = [];
        const addressBar = createAddressBar('#/');
        watchSignInLinks(addressBar, (token) => tokens.push(token));
        addressBar.navigate('#/login');
        addressBar.dispatch('popstate');
      });

      it('should not sign in', () => {
        assert.deepEqual(tokens, []);
      });
    });
  });
});
