import { hasQueueMoved, queueKeyOf, type ServerStatus } from '../domain/server-status.ts';
import type { EngineStatus } from './engine-status.ts';

export interface QueueWatchStart {
  readonly from: ServerStatus | null;
}

export const watchQueueMoves = (
  engineStatus: Pick<EngineStatus, 'subscribe' | 'getSnapshot'>,
  onMove: () => void,
  { from }: QueueWatchStart,
): (() => void) => {
  let lastKey = queueKeyOf(from);
  return engineStatus.subscribe(() => {
    const key = queueKeyOf(engineStatus.getSnapshot().status);
    if (key === null) return;
    if (hasQueueMoved(lastKey, key)) onMove();
    lastKey = key;
  });
};
