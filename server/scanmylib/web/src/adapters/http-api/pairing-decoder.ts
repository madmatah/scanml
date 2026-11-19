import type { PairingDetails } from '../../domain/pairing-details.ts';
import { readResponseFields } from './response-fields.ts';

export const decodePairingDetails = (body: unknown): PairingDetails => {
  const pairing = readResponseFields(body);
  return {
    serverUrl: pairing.string('url'),
    accessToken: pairing.string('token'),
    isApkAvailable: pairing.boolean('apk_available'),
    apkUrl: pairing.string('apk_url'),
  };
};
