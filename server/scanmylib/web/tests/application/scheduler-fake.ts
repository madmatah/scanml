import type { Scheduler } from '../../src/application/scheduler.ts';

interface ScheduledTask {
  readonly task: () => void;
  readonly delayMilliseconds: number;
  isPending: boolean;
}

export interface FakeScheduler extends Scheduler {
  readonly pendingDelaysMilliseconds: () => number[];
  readonly runPending: () => void;
}

// Time passes only when a test runs the tasks still pending, so that no test waits.
export function createFakeScheduler(): FakeScheduler {
  const tasks: ScheduledTask[] = [];
  return {
    schedule(task, delayMilliseconds) {
      const scheduled: ScheduledTask = { task, delayMilliseconds, isPending: true };
      tasks.push(scheduled);
      return () => {
        scheduled.isPending = false;
      };
    },
    pendingDelaysMilliseconds: () => tasks.filter((task) => task.isPending).map((task) => task.delayMilliseconds),
    runPending() {
      for (const scheduled of tasks.filter((task) => task.isPending)) {
        scheduled.isPending = false;
        scheduled.task();
      }
    },
  };
}
