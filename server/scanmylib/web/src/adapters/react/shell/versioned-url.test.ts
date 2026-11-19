import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { versionedUrl } from './versioned-url.ts';

const VERSION = '2026-11-14T15:41:03+00:00';

describe('The versioned url', () => {
  describe('The versionedUrl() function', () => {
    describe('When the address has no query', () => {
      let url: string;
      beforeEach(() => {
        url = versionedUrl('/api/pages/page-1/thumb', VERSION);
      });

      it('should add the version as its query, escaped', () => {
        assert.equal(url, '/api/pages/page-1/thumb?v=2026-11-14T15%3A41%3A03%2B00%3A00');
      });
    });

    describe('When the address already has a query', () => {
      let url: string;
      beforeEach(() => {
        url = versionedUrl('/api/pages/page-1/thumb?size=small', VERSION);
      });

      it('should add the version to it', () => {
        assert.equal(url, '/api/pages/page-1/thumb?size=small&v=2026-11-14T15%3A41%3A03%2B00%3A00');
      });
    });
  });
});
