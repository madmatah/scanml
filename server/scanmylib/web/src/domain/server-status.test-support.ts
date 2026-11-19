import type { EngineReport, QueueCounts, ServerStatus } from './server-status.ts';

export interface StatusChanges {
  readonly engine?: Partial<EngineReport>;
  readonly queue?: Partial<QueueCounts>;
  readonly libraryDirectory?: string;
}

export function sampleServerStatus(changes: StatusChanges = {}): ServerStatus {
  return {
    version: '0.2.3',
    engine: {
      isReachable: true,
      state: 'ready',
      backend: 'vllm',
      lastError: null,
      graphicsCard: { name: 'Example GPU', memoryUsedMebibytes: 4608, memoryTotalMebibytes: 8192 },
      ...changes.engine,
    },
    queue: { queuedCount: 3, processingCount: 1, errorCount: 0, doneCount: 1200, ...changes.queue },
    libraryDirectory: changes.libraryDirectory ?? '/home/user/Documents/ScanMyLib',
  };
}
