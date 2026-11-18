export type CancelTask = () => void;

export interface Scheduler {
  schedule(task: () => void, delayMilliseconds: number): CancelTask;
}
