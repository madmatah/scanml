import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import {
  type Access,
  type AddressIds,
  documentPath,
  documentTitle,
  idOfAddress,
  pagePath,
  type Redirect,
  type RouteName,
  readerPath,
  redirectFor,
  routeNameOf,
  type Section,
  sectionOf,
} from './navigation.ts';

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
        path: '/no-such-screen',
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
        situation: 'When a signed-in browser is on the pairing',
        access: 'signed-in',
        route: 'pairing',
        path: '/pairing',
        rule: 'should stay there',
        expectedRedirect: null,
      },
      {
        situation: 'When a signed-out browser opens a document',
        access: 'signed-out',
        route: 'document',
        path: '/documents/95bbeb79-4351-432f-a53c-d3658892ff50',
        rule: 'should go to the login, and come back to the document once signed in',
        expectedRedirect: {
          to: 'login',
          returnTo: '/documents/95bbeb79-4351-432f-a53c-d3658892ff50',
          replacesEntry: true,
        },
      },
      {
        situation: 'When a signed-out browser opens the pairing',
        access: 'signed-out',
        route: 'pairing',
        path: '/pairing',
        rule: 'should go to the login, and come back to the pairing once signed in',
        expectedRedirect: { to: 'login', returnTo: '/pairing', replacesEntry: true },
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
        path: '/no-such-screen',
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
        situation: 'When the route is a document',
        route: 'document',
        rule: 'should be the library, which the document belongs to',
        expectedSection: 'library',
      },
      {
        situation: 'When the route is the reader',
        route: 'reader',
        rule: 'should be the library, which the document read belongs to',
        expectedSection: 'library',
      },
      {
        situation: 'When the route is a page',
        route: 'page',
        rule: 'should be the library, which the page belongs to',
        expectedSection: 'library',
      },
      {
        situation: 'When the route is the pairing',
        route: 'pairing',
        rule: 'should be the pairing, so that the header marks it as current',
        expectedSection: 'pairing',
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

  describe('The documentPath() function', () => {
    let path: string;
    beforeEach(() => {
      path = documentPath('95bbeb79-4351-432f-a53c-d3658892ff50');
    });

    it('should be the address of the document screen, as the earlier releases named it', () => {
      assert.equal(path, '/documents/95bbeb79-4351-432f-a53c-d3658892ff50');
    });
  });

  describe('The routeNameOf() function', () => {
    const rows: { situation: string; matchedId: string; ids: AddressIds; expected: RouteName }[] = [
      {
        situation: 'When the address names a document by its id',
        matchedId: 'document',
        ids: { documentId: '95bbeb79-4351-432f-a53c-d3658892ff50' },
        expected: 'document',
      },
      {
        situation: 'When the address names a document by something else than an id',
        matchedId: 'document',
        ids: { documentId: 'example-book' },
        expected: 'unknown',
      },
      {
        situation: 'When the address names the reader of a document by its id',
        matchedId: 'reader',
        ids: { documentId: '95bbeb79-4351-432f-a53c-d3658892ff50' },
        expected: 'reader',
      },
      {
        situation: 'When the address names the reader of a document by something else than an id',
        matchedId: 'reader',
        ids: { documentId: 'example-book' },
        expected: 'unknown',
      },
      {
        situation: 'When the address names a page by its id',
        matchedId: 'page',
        ids: { pageId: 'de215798-031a-4b20-a867-49c12e3baabe' },
        expected: 'page',
      },
      {
        situation: 'When the address names a page by something else than an id',
        matchedId: 'page',
        ids: { pageId: 'p0011' },
        expected: 'unknown',
      },
      { situation: 'When the route is the pairing', matchedId: 'pairing', ids: {}, expected: 'pairing' },
      { situation: 'When the route has no name', matchedId: '0-1', ids: {}, expected: 'unknown' },
    ];

    for (const { situation, matchedId, ids, expected } of rows) {
      describe(situation, () => {
        let route: RouteName;
        beforeEach(() => {
          route = routeNameOf(matchedId, ids);
        });

        it(`should be ${expected}`, () => {
          assert.equal(route, expected);
        });
      });
    }
  });

  describe('The idOfAddress() function', () => {
    describe('When the address writes the id in capitals', () => {
      let id: string | null;
      beforeEach(() => {
        id = idOfAddress('95BBEB79-4351-432F-A53C-D3658892FF50');
      });

      it('should give it in lowercase, as the api names it', () => {
        assert.equal(id, '95bbeb79-4351-432f-a53c-d3658892ff50');
      });
    });

    describe('When the address holds something else than an id', () => {
      let id: string | null;
      beforeEach(() => {
        id = idOfAddress('95bbeb79-4351-432f-a53c-d3658892ff50/../pairing');
      });

      it('should give none', () => {
        assert.equal(id, null);
      });
    });
  });

  describe('The readerPath() function', () => {
    let path: string;
    beforeEach(() => {
      path = readerPath('95bbeb79-4351-432f-a53c-d3658892ff50');
    });

    it('should be the address of the reader, as the earlier releases named it', () => {
      assert.equal(path, '/documents/95bbeb79-4351-432f-a53c-d3658892ff50/read');
    });
  });

  describe('The pagePath() function', () => {
    let path: string;
    beforeEach(() => {
      path = pagePath('de215798-031a-4b20-a867-49c12e3baabe');
    });

    it('should be the address of the page screen, as the earlier releases named it', () => {
      assert.equal(path, '/pages/de215798-031a-4b20-a867-49c12e3baabe');
    });
  });
});
