import type { Scheduler } from '../../application/scheduler.ts';

export interface Timers {
  setTimeout(task: () => void, delayMilliseconds: number): number;
  clearTimeout(timer: number): void;
}

export function createTimerScheduler(timers: Timers): Scheduler {
  return {
    schedule(task, delayMilliseconds) {
      const timer = timers.setTimeout(task, delayMilliseconds);
      return () => timers.clearTimeout(timer);
    },
  };
}
