import type { UuidSource } from '../../application/uuid-source.ts';

export interface RandomValues {
  getRandomValues(array: Uint8Array<ArrayBuffer>): Uint8Array<ArrayBuffer>;
}

const UUID_BYTES = 16;
const VERSION_BYTE = 6;
const VARIANT_BYTE = 8;

// crypto.randomUUID() exists only in a secure context, and the web UI is usually opened over plain HTTP on the local
// network, where crypto.getRandomValues() is still there: the UUID (version 4, RFC 9562) is built from its bytes.
export function createRandomUuidSource(random: RandomValues): UuidSource {
  return {
    createUuid() {
      const bytes = random.getRandomValues(new Uint8Array(UUID_BYTES));
      bytes[VERSION_BYTE] = ((bytes[VERSION_BYTE] ?? 0) & 0x0f) | 0x40;
      bytes[VARIANT_BYTE] = ((bytes[VARIANT_BYTE] ?? 0) & 0x3f) | 0x80;
      const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
      return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    },
  };
}
