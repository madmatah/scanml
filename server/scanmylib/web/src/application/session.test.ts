import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { ApiError, NetworkError } from './api-errors.ts';
import {
  createFakeSessionServer,
  createFakeSignInRecord,
  type FakeSessionServer,
  type FakeSignInRecord,
  type ServerAnswers,
} from './session.test-support.ts';
import { createSession, type Session, type SessionState } from './session.ts';

const UNAUTHORIZED = 401;
const SERVER_FAILURE = 500;
const TOKEN = 'a-token';
const SIGNED_IN: SessionState = { phase: 'signed-in' };
const SIGNED_OUT: SessionState = { phase: 'signed-out', notice: null };

interface Arrangement {
  readonly server: FakeSessionServer;
  readonly signInRecord: FakeSignInRecord;
  readonly session: Session;
}

const arrange = (recorded: boolean | null, answers: ServerAnswers = {}): Arrangement => {
  const server = createFakeSessionServer(answers);
  const signInRecord = createFakeSignInRecord(recorded);
  return { server, signInRecord, session: createSession(server, signInRecord) };
};

const startSignedIn = async (answers: ServerAnswers = {}): Promise<Arrangement> => {
  const arrangement = arrange(true, answers);
  await arrangement.session.start(null);
  arrangement.server.calls.length = 0;
  return arrangement;
};

describe('The session', () => {
  describe('The getSnapshot() method', () => {
    describe('When the session has not started', () => {
      let state: SessionState;
      beforeEach(() => {
        state = arrange(true).session.getSnapshot();
      });

      it('should say that it is loading, so that no screen shows before the api answers', () => {
        assert.deepEqual(state, { phase: 'loading' });
      });
    });

    describe('When nothing changed since the last snapshot', () => {
      let first: SessionState;
      let second: SessionState;
      beforeEach(async () => {
        const { session } = arrange(true);
        await session.start(null);
        first = session.getSnapshot();
        second = session.getSnapshot();
      });

      it('should give the same state, so that React does not render again', () => {
        assert.equal(second, first);
      });
    });
  });

  describe('The start() method', () => {
    describe('When this browser has not signed in', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(false);
        await arrangement.session.start(null);
      });

      it('should be signed out without a notice', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), SIGNED_OUT);
      });

      it('should not ask the api, so that a first visit logs no refused request', () => {
        assert.deepEqual(arrangement.server.calls, []);
      });
    });

    describe('When this browser has signed in and its session is still valid', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(true);
        await arrangement.session.start(null);
      });

      it('should ask the api', () => {
        assert.deepEqual(arrangement.server.calls, ['checkSession']);
      });

      it('should be signed in', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), SIGNED_IN);
      });
    });

    describe('When the record of a sign-in cannot be read', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(null);
        await arrangement.session.start(null);
      });

      it('should ask the api, since this browser may have signed in', () => {
        assert.deepEqual(arrangement.server.calls, ['checkSession']);
      });
    });

    describe('When the api no longer knows the session', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(true, { checkSession: new ApiError(UNAUTHORIZED, 'unauthorized') });
        await arrangement.session.start(null);
      });

      it('should be signed out without a notice', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), SIGNED_OUT);
      });

      it('should forget the sign-in, so that the next visit shows the login at once', () => {
        assert.equal(arrangement.signInRecord.recorded(), false);
      });
    });

    describe('When the api cannot be reached', () => {
      const failure = new NetworkError();
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(true, { checkSession: failure });
        await arrangement.session.start(null);
      });

      it('should be signed out, with a notice of the failed check that holds the failure', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), {
          phase: 'signed-out',
          notice: { reason: 'check-failed', failure },
        });
      });

      it('should keep the sign-in, so that the next visit asks the api again', () => {
        assert.equal(arrangement.signInRecord.recorded(), true);
      });
    });

    describe('When a sign-in link gives a token that the api accepts', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(false);
        await arrangement.session.start(TOKEN);
      });

      it('should sign in with the token', () => {
        assert.deepEqual(arrangement.server.calls, [`signIn ${TOKEN}`]);
      });

      it('should be signed in', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), SIGNED_IN);
      });

      it('should record the sign-in', () => {
        assert.equal(arrangement.signInRecord.recorded(), true);
      });
    });

    describe('When a sign-in link gives a token that the api refuses', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(false, { signIn: new ApiError(UNAUTHORIZED, 'invalid token') });
        await arrangement.session.start(TOKEN);
      });

      it('should be signed out, with a notice of the refused link', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), {
          phase: 'signed-out',
          notice: { reason: 'link-refused' },
        });
      });
    });

    describe('When a sign-in link gives a refused token, but the session of this browser is still valid', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(true, { signIn: new ApiError(UNAUTHORIZED, 'invalid token') });
        await arrangement.session.start(TOKEN);
      });

      it('should stay signed in, since a valid session wins over a stale link', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), SIGNED_IN);
      });
    });

    describe('When a sign-in link gives a refused token, and the api no longer knows the session of this browser', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(true, {
          signIn: new ApiError(UNAUTHORIZED, 'invalid token'),
          checkSession: new ApiError(UNAUTHORIZED, 'unauthorized'),
        });
        await arrangement.session.start(TOKEN);
      });

      it('should be signed out, with a notice of the refused link', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), {
          phase: 'signed-out',
          notice: { reason: 'link-refused' },
        });
      });
    });

    describe('When a sign-in link cannot reach the api', () => {
      const failure = new NetworkError();
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(false, { signIn: failure });
        await arrangement.session.start(TOKEN);
      });

      it('should be signed out, with a notice of the failed link that holds the failure', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), {
          phase: 'signed-out',
          notice: { reason: 'link-failed', failure },
        });
      });
    });
  });

  describe('The signInWithLink() method', () => {
    describe('When the session is signed in and the api refuses the token of the link', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = await startSignedIn({ signIn: new ApiError(UNAUTHORIZED, 'invalid token') });
        await arrangement.session.signInWithLink(TOKEN);
      });

      it('should check the session after the refused link', () => {
        assert.deepEqual(arrangement.server.calls, [`signIn ${TOKEN}`, 'checkSession']);
      });

      it('should stay signed in', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), SIGNED_IN);
      });
    });

    describe('When the session is signed out and the api accepts the token of the link', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(false);
        await arrangement.session.start(null);
        await arrangement.session.signInWithLink(TOKEN);
      });

      it('should be signed in', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), SIGNED_IN);
      });
    });
  });

  describe('The signIn() method', () => {
    describe('When the api accepts the token', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(false);
        await arrangement.session.start(null);
        await arrangement.session.signIn(TOKEN);
      });

      it('should sign in with the token', () => {
        assert.deepEqual(arrangement.server.calls, [`signIn ${TOKEN}`]);
      });

      it('should be signed in', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), SIGNED_IN);
      });

      it('should record the sign-in', () => {
        assert.equal(arrangement.signInRecord.recorded(), true);
      });
    });

    describe('When the api refuses the token', () => {
      const failure = new ApiError(UNAUTHORIZED, 'invalid token');
      let arrangement: Arrangement;
      let act: () => Promise<void>;
      beforeEach(async () => {
        arrangement = arrange(false, { signIn: failure });
        await arrangement.session.start(null);
        act = () => arrangement.session.signIn(TOKEN);
      });

      it('should fail with the refusal of the api, so that the login explains it', async () => {
        await assert.rejects(act(), { name: 'ApiError', message: /invalid token/ });
      });
    });

    describe('When the api refuses the token and the login has explained it', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(false, { signIn: new ApiError(UNAUTHORIZED, 'invalid token') });
        await arrangement.session.start(null);
        await arrangement.session.signIn(TOKEN).catch(() => undefined);
      });

      it('should stay signed out', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), SIGNED_OUT);
      });
    });
  });

  describe('The signOut() method', () => {
    describe('When the api closes the session', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = await startSignedIn();
        await arrangement.session.signOut();
      });

      it('should be signed out without a notice', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), SIGNED_OUT);
      });

      it('should forget the sign-in', () => {
        assert.equal(arrangement.signInRecord.recorded(), false);
      });
    });

    describe('When the api refuses to close the session', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = await startSignedIn({ signOut: new ApiError(SERVER_FAILURE, 'internal error') });
        await arrangement.session.signOut();
      });

      it('should be signed out all the same, since the session can no longer be used', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), SIGNED_OUT);
      });

      it('should forget the sign-in', () => {
        assert.equal(arrangement.signInRecord.recorded(), false);
      });
    });

    describe('When the api cannot be reached', () => {
      let arrangement: Arrangement;
      let act: () => Promise<void>;
      beforeEach(async () => {
        arrangement = await startSignedIn({ signOut: new NetworkError() });
        act = () => arrangement.session.signOut();
      });

      it('should fail with the network failure, so that the screen can say it', async () => {
        await assert.rejects(act(), { name: 'NetworkError', message: /Network error/ });
      });
    });

    describe('When the api cannot be reached and the screen has said it', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = await startSignedIn({ signOut: new NetworkError() });
        await arrangement.session.signOut().catch(() => undefined);
      });

      it('should stay signed in, since the session still holds', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), SIGNED_IN);
      });

      it('should keep the sign-in', () => {
        assert.equal(arrangement.signInRecord.recorded(), true);
      });
    });
  });

  describe('The expire() method', () => {
    describe('When the session is signed in', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = await startSignedIn();
        arrangement.session.expire();
      });

      it('should be signed out, with a notice of the expired session', () => {
        assert.deepEqual(arrangement.session.getSnapshot(), { phase: 'signed-out', notice: { reason: 'expired' } });
      });

      it('should forget the sign-in, so that the next visit shows the login at once', () => {
        assert.equal(arrangement.signInRecord.recorded(), false);
      });
    });

    describe('When the session is still loading', () => {
      let session: Session;
      beforeEach(() => {
        ({ session } = arrange(true));
        session.expire();
      });

      it('should keep loading, since the check of the session decides', () => {
        assert.deepEqual(session.getSnapshot(), { phase: 'loading' });
      });
    });

    describe('When the session is signed out with a notice', () => {
      let session: Session;
      beforeEach(async () => {
        ({ session } = arrange(false, { signIn: new ApiError(UNAUTHORIZED, 'invalid token') }));
        await session.start(TOKEN);
        session.expire();
      });

      it('should keep its notice, which says why the login shows', () => {
        assert.deepEqual(session.getSnapshot(), { phase: 'signed-out', notice: { reason: 'link-refused' } });
      });
    });
  });

  describe('The dismissNotice() method', () => {
    describe('When the session is signed out with a notice', () => {
      let session: Session;
      beforeEach(async () => {
        ({ session } = arrange(false, { signIn: new ApiError(UNAUTHORIZED, 'invalid token') }));
        await session.start(TOKEN);
        session.dismissNotice();
      });

      it('should drop the notice, so that the login shows it once', () => {
        assert.deepEqual(session.getSnapshot(), SIGNED_OUT);
      });
    });
  });

  describe('The subscribe() method', () => {
    describe('When the state changes', () => {
      let notifications: number;
      beforeEach(async () => {
        notifications = 0;
        const { session } = arrange(true);
        session.subscribe(() => {
          notifications += 1;
        });
        await session.start(null);
      });

      it('should tell the listener', () => {
        assert.equal(notifications, 1);
      });
    });

    describe('When the listener has unsubscribed before the state changes', () => {
      let notifications: number;
      beforeEach(async () => {
        notifications = 0;
        const { session } = arrange(true);
        const unsubscribe = session.subscribe(() => {
          notifications += 1;
        });
        unsubscribe();
        await session.start(null);
      });

      it('should no longer tell it', () => {
        assert.equal(notifications, 0);
      });
    });
  });
});
