import type { UuidSource } from './uuid-source.ts';

// Page ids that tell in which order they were made.
export const createCountingUuidSource = (): UuidSource => {
  let count = 0;
  return {
    createUuid() {
      count += 1;
      return `00000000-0000-4000-8000-${String(count).padStart(12, '0')}`;
    },
  };
};
