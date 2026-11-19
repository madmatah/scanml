import type { SessionServer, SignInRecord } from './session.ts';

export interface ServerAnswers {
  readonly checkSession?: Error;
  readonly signIn?: Error;
  readonly signOut?: Error;
}

export interface FakeSessionServer extends SessionServer {
  readonly calls: string[];
}

export const createFakeSessionServer = (answers: ServerAnswers = {}): FakeSessionServer => {
  const calls: string[] = [];
  const answer = async (call: string, failure: Error | undefined): Promise<void> => {
    calls.push(call);
    if (failure !== undefined) throw failure;
  };
  return {
    calls,
    checkSession: () => answer('checkSession', answers.checkSession),
    signIn: (token) => answer(`signIn ${token}`, answers.signIn),
    signOut: () => answer('signOut', answers.signOut),
  };
};

export interface FakeSignInRecord extends SignInRecord {
  readonly recorded: () => boolean | null;
}

// A record that cannot be read, as a disabled storage, also keeps nothing written to it.
export const createFakeSignInRecord = (recorded: boolean | null): FakeSignInRecord => {
  let current = recorded;
  return {
    recorded: () => current,
    readRecorded: () => current,
    record(isSignedIn) {
      if (current !== null) current = isSignedIn;
    },
  };
};
