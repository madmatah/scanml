import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import {
  type Access,
  documentTitle,
  type Redirect,
  type RouteName,
  redirectFor,
  type Section,
  sectionOf,
} from '../../../../src/adapters/react/shell/navigation.ts';

describe('The navigation', () => {
  describe('The redirectFor() function', () => {
    const situations: {
      situation: string;
      access: Access;
      route: RouteName;
      path: string;
      rule: string;
      expectedRedirect: Redirect | null;
    }[] = [
      {
        situation: 'When a signed-out browser opens a screen',
        access: 'signed-out',
        route: 'home',
        path: '/',
        rule: 'should go to the login, and come back to the screen once signed in',
        expectedRedirect: { to: 'login', returnTo: '/', replacesEntry: true },
      },
      {
        situation: 'When a signed-out browser opens an unknown address',
        access: 'signed-out',
        route: 'unknown',
        path: '/pairing',
        rule: 'should go to the login, and to the home once signed in',
        expectedRedirect: { to: 'login', returnTo: null, replacesEntry: true },
      },
      {
        situation: 'When a signed-out browser is on the login',
        access: 'signed-out',
        route: 'login',
        path: '/login',
        rule: 'should stay there',
        expectedRedirect: null,
      },
      {
        situation: 'When the user has just signed out from a screen',
        access: 'just-signed-out',
        route: 'home',
        path: '/',
        rule: 'should go to the login as a new entry of the history, and to the home once signed in again',
        expectedRedirect: { to: 'login', returnTo: null, replacesEntry: false },
      },
      {
        situation: 'When the user has just signed out and is on the login',
        access: 'just-signed-out',
        route: 'login',
        path: '/login',
        rule: 'should stay there',
        expectedRedirect: null,
      },
      {
        situation: 'When a signed-in browser is on a screen',
        access: 'signed-in',
        route: 'home',
        path: '/',
        rule: 'should stay there',
        expectedRedirect: null,
      },
      {
        situation: 'When a signed-in browser is on the login',
        access: 'signed-in',
        route: 'login',
        path: '/login',
        rule: 'should go back to the screen it came from',
        expectedRedirect: { to: 'return-path' },
      },
      {
        situation: 'When a signed-in browser opens an unknown address',
        access: 'signed-in',
        route: 'unknown',
        path: '/pairing',
        rule: 'should go to the screen it came from, or the home',
        expectedRedirect: { to: 'return-path' },
      },
    ];

    for (const { situation, access, route, path, rule, expectedRedirect } of situations) {
      describe(situation, () => {
        let redirect: Redirect | null;
        beforeEach(() => {
          redirect = redirectFor(access, route, path);
        });

        it(rule, () => {
          assert.deepEqual(redirect, expectedRedirect);
        });
      });
    }
  });

  describe('The sectionOf() function', () => {
    const routes: { situation: string; route: RouteName; rule: string; expectedSection: Section | null }[] = [
      {
        situation: 'When the route is the home',
        route: 'home',
        rule: 'should be the library, so that the header marks it as current',
        expectedSection: 'library',
      },
      {
        situation: 'When the route is the login',
        route: 'login',
        rule: 'should be none, since the header does not show',
        expectedSection: null,
      },
      {
        situation: 'When the route is unknown',
        route: 'unknown',
        rule: 'should be none, since the screen redirects',
        expectedSection: null,
      },
    ];

    for (const { situation, route, rule, expectedSection } of routes) {
      describe(situation, () => {
        let section: Section | null;
        beforeEach(() => {
          section = sectionOf(route);
        });

        it(rule, () => {
          assert.equal(section, expectedSection);
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
