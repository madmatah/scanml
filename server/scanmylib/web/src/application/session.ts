import { ApiError } from './api-errors.ts';

export interface SessionServer {
  checkSession(): Promise<void>;
  signIn(token: string): Promise<void>;
  signOut(): Promise<void>;
}

export interface SignInRecord {
  readRecorded(): boolean | null;
  record(isSignedIn: boolean): void;
}

export type SignedOutNotice =
  | { readonly reason: 'expired' }
  | { readonly reason: 'link-refused' }
  | { readonly reason: 'link-failed'; readonly failure: unknown }
  | { readonly reason: 'check-failed'; readonly failure: unknown };

export type SessionState =
  | { readonly phase: 'loading' }
  | { readonly phase: 'signed-in' }
  | { readonly phase: 'signed-out'; readonly notice: SignedOutNotice | null };

export interface Session {
  subscribe(listener: () => void): () => void;
  getSnapshot(): SessionState;
  start(linkToken: string | null): Promise<void>;
  signIn(token: string): Promise<void>;
  signInWithLink(token: string): Promise<void>;
  signOut(): Promise<void>;
  expire(): void;
  dismissNotice(): void;
}

const LOADING: SessionState = { phase: 'loading' };
const SIGNED_IN: SessionState = { phase: 'signed-in' };
const SIGNED_OUT: SessionState = { phase: 'signed-out', notice: null };
const UNAUTHORIZED = 401;

function isUnauthorized(failure: unknown): boolean {
  return failure instanceof ApiError && failure.status === UNAUTHORIZED;
}

export function createSession(server: SessionServer, signInRecord: SignInRecord): Session {
  let state = LOADING;
  const listeners = new Set<() => void>();

  function enter(next: SessionState): void {
    state = next;
    for (const listener of listeners) listener();
  }

  function mayBeSignedIn(): boolean {
    return signInRecord.readRecorded() !== false;
  }

  async function stateAfterCheck(): Promise<SessionState> {
    try {
      await server.checkSession();
      return SIGNED_IN;
    } catch (failure) {
      if (isUnauthorized(failure)) {
        signInRecord.record(false);
        return SIGNED_OUT;
      }
      return { phase: 'signed-out', notice: { reason: 'check-failed', failure } };
    }
  }

  async function stateAfterLink(token: string): Promise<SessionState> {
    try {
      await server.signIn(token);
      signInRecord.record(true);
      return SIGNED_IN;
    } catch (failure) {
      if (mayBeSignedIn() && (await stateAfterCheck()) === SIGNED_IN) return SIGNED_IN;
      const notice: SignedOutNotice = isUnauthorized(failure)
        ? { reason: 'link-refused' }
        : { reason: 'link-failed', failure };
      return { phase: 'signed-out', notice };
    }
  }

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    getSnapshot: () => state,
    async start(linkToken) {
      if (linkToken !== null) enter(await stateAfterLink(linkToken));
      else if (mayBeSignedIn()) enter(await stateAfterCheck());
      else enter(SIGNED_OUT);
    },
    async signIn(token) {
      await server.signIn(token);
      signInRecord.record(true);
      enter(SIGNED_IN);
    },
    async signInWithLink(token) {
      enter(await stateAfterLink(token));
    },
    async signOut() {
      try {
        await server.signOut();
      } catch (failure) {
        if (!(failure instanceof ApiError)) throw failure;
      }
      signInRecord.record(false);
      enter(SIGNED_OUT);
    },
    expire() {
      if (state.phase !== 'signed-in') return;
      signInRecord.record(false);
      enter({ phase: 'signed-out', notice: { reason: 'expired' } });
    },
    dismissNotice() {
      if (state.phase === 'signed-out' && state.notice !== null) enter(SIGNED_OUT);
    },
  };
}
