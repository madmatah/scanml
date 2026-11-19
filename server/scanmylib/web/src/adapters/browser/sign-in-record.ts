import type { SignInRecord } from '../../application/session.ts';

export interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

// Names outside the program: every browser signed in before keeps them, and a new one would show it the login.
const SIGNED_IN_KEY = 'scanmylib.signed-in';
const SIGNED_IN = '1';

// The storage is reached on each call, since the browser throws when its storage is disabled, even on reaching it.
export const createSignInRecord = (openStorage: () => KeyValueStorage): SignInRecord => {
  return {
    readRecorded() {
      try {
        return openStorage().getItem(SIGNED_IN_KEY) === SIGNED_IN;
      } catch {
        return null;
      }
    },
    record(isSignedIn) {
      try {
        if (isSignedIn) openStorage().setItem(SIGNED_IN_KEY, SIGNED_IN);
        else openStorage().removeItem(SIGNED_IN_KEY);
      } catch {
        // A disabled storage remembers nothing, and the next visit asks the api.
      }
    },
  };
};
