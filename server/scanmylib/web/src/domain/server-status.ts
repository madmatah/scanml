export interface GraphicsCard {
  readonly name: string | null;
  readonly memoryUsedMebibytes: number | null;
  readonly memoryTotalMebibytes: number | null;
}

export interface EngineReport {
  readonly isReachable: boolean;
  readonly state: string | null;
  readonly backend: string | null;
  readonly lastError: string | null;
  readonly graphicsCard: GraphicsCard | null;
}

export interface QueueCounts {
  readonly queuedCount: number;
  readonly processingCount: number;
  readonly errorCount: number;
  readonly doneCount: number;
}

export interface ServerStatus {
  readonly version: string;
  readonly engine: EngineReport;
  readonly queue: QueueCounts;
  readonly libraryDirectory: string;
}

export const countPendingPages = (queue: QueueCounts): number => {
  return queue.queuedCount + queue.processingCount;
};

export const queueKeyOf = (status: ServerStatus | null): string | null => {
  if (status === null) return null;
  const { queuedCount, processingCount, doneCount, errorCount } = status.queue;
  return [queuedCount, processingCount, doneCount, errorCount].join('/');
};

export const hasQueueMoved = (previousKey: string | null, key: string): boolean => {
  return previousKey !== null && key !== previousKey;
};
