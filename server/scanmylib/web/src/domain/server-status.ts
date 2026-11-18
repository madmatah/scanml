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

export function countPendingPages(queue: QueueCounts): number {
  return queue.queuedCount + queue.processingCount;
}
