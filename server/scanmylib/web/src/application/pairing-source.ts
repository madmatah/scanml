import type { PairingDetails } from '../domain/pairing-details.ts';

export interface PairingSource {
  readonly pairingQrCodeUrl: string;
  readonly apkQrCodeUrl: string;
  readonly apkDownloadUrl: string;
  readPairing(signal: AbortSignal): Promise<PairingDetails>;
}
