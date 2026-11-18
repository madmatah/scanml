import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import {
  documentTitle,
  type Redirect,
  type RouteName,
  redirectFor,
} from '../../../../src/adapters/react/shell/navigation.ts';

describe('The navigation', () => {
  describe('The redirectFor() function', () => {
    const situations: {
      situation: string;
      isSignedIn: boolean;
      route: RouteName;
      path: string;
      rule: string;
      expectedRedirect: Redirect | null;
    }[] = [
      {
        situation: 'When a signed-out browser opens a screen',
        isSignedIn: false,
        route: 'home',
        path: '/',
        rule: 'should go to the login, and come back to the screen once signed in',
        expectedRedirect: { to: 'login', returnTo: '/' },
      },
      {
        situation: 'When a signed-out browser opens an unknown address',
        isSignedIn: false,
        route: 'unknown',
        path: '/pairing',
        rule: 'should go to the login, and to the home once signed in',
        expectedRedirect: { to: 'login', returnTo: null },
      },
      {
        situation: 'When a signed-out browser is on the login',
        isSignedIn: false,
        route: 'login',
        path: '/login',
        rule: 'should stay there',
        expectedRedirect: null,
      },
      {
        situation: 'When a signed-in browser is on a screen',
        isSignedIn: true,
        route: 'home',
        path: '/',
        rule: 'should stay there',
        expectedRedirect: null,
      },
      {
        situation: 'When a signed-in browser is on the login',
        isSignedIn: true,
        route: 'login',
        path: '/login',
        rule: 'should go back to the screen it came from',
        expectedRedirect: { to: 'return-path' },
      },
      {
        situation: 'When a signed-in browser opens an unknown address',
        isSignedIn: true,
        route: 'unknown',
        path: '/pairing',
        rule: 'should go to the screen it came from, or the home',
        expectedRedirect: { to: 'return-path' },
      },
    ];

    for (const { situation, isSignedIn, route, path, rule, expectedRedirect } of situations) {
      describe(situation, () => {
        let redirect: Redirect | null;
        beforeEach(() => {
          redirect = redirectFor(isSignedIn, route, path);
        });

        it(rule, () => {
          assert.deepEqual(redirect, expectedRedirect);
        });
      });
    }
  });

  describe('The documentTitle() function', () => {
    describe('When the screen has a title', () => {
      let title: string;
      beforeEach(() => {
        title = documentTitle('Sign in');
      });

      it('should put it before the name of the product', () => {
        assert.equal(title, 'Sign in · ScanMyLib');
      });
    });

    describe('When the screen has no title', () => {
      let title: string;
      beforeEach(() => {
        title = documentTitle(null);
      });

      it('should be the name of the product', () => {
        assert.equal(title, 'ScanMyLib');
      });
    });
  });
});
