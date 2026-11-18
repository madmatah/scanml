import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { decodePairingDetails } from '../../../src/adapters/http-api/pairing-decoder.ts';
import type { PairingDetails } from '../../../src/domain/pairing-details.ts';

// The answer of GET /api/pairing, as docs/API.md gives it.
function pairingBody(): Record<string, unknown> {
  return {
    url: 'http://192.168.1.10:8765',
    token: 'EXAMPLE-TOKEN',
    pair_uri: 'scanmylib://pair?url=http%3A%2F%2F192.168.1.10%3A8765&token=EXAMPLE-TOKEN',
    apk_available: true,
    apk_url: 'http://192.168.1.10:8765/download/scanmylib.apk',
  };
}

describe('The pairing decoder', () => {
  describe('The decodePairingDetails() function', () => {
    describe('When the answer has the documented shape', () => {
      let pairing: PairingDetails;
      beforeEach(() => {
        pairing = decodePairingDetails(pairingBody());
      });

      it('should give each field the pairing screen shows its value, and leave out the link the QR code holds', () => {
        assert.deepEqual(pairing, {
          serverUrl: 'http://192.168.1.10:8765',
          accessToken: 'EXAMPLE-TOKEN',
          isApkAvailable: true,
          apkUrl: 'http://192.168.1.10:8765/download/scanmylib.apk',
        });
      });
    });

    describe('When the answer holds a field the client does not know', () => {
      let pairing: PairingDetails;
      beforeEach(() => {
        pairing = decodePairingDetails({ ...pairingBody(), apk_version: '0.9.0' });
      });

      it('should ignore it, so that the api can grow without breaking the UI', () => {
        assert.equal(pairing.accessToken, 'EXAMPLE-TOKEN');
      });
    });

    describe('When the answer lacks a field', () => {
      let act: () => PairingDetails;
      beforeEach(() => {
        const { token: _token, ...body } = pairingBody();
        act = () => decodePairingDetails(body);
      });

      it('should refuse it, naming the field', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid token" });
      });
    });

    describe('When a field has the wrong type', () => {
      let act: () => PairingDetails;
      beforeEach(() => {
        act = () => decodePairingDetails({ ...pairingBody(), apk_available: 'yes' });
      });

      it('should refuse it, naming the field', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid apk_available" });
      });
    });
  });
});
