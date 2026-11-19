import type { GraphicsCard, ServerStatus } from '../../domain/server-status.ts';
import { type ResponseFields, readResponseFields } from './response-fields.ts';

const decodeGraphicsCard = (gpu: ResponseFields | null): GraphicsCard | null => {
  if (gpu === null) return null;
  return {
    name: gpu.nullableString('name'),
    memoryUsedMebibytes: gpu.nullableNumber('memory_used_mb'),
    memoryTotalMebibytes: gpu.nullableNumber('memory_total_mb'),
  };
};

export const decodeServerStatus = (body: unknown): ServerStatus => {
  const status = readResponseFields(body);
  const ocr = status.object('ocr');
  const queue = status.object('queue');
  return {
    version: status.string('version'),
    engine: {
      isReachable: ocr.boolean('reachable'),
      state: ocr.nullableString('state'),
      backend: ocr.nullableString('backend'),
      lastError: ocr.nullableString('last_error'),
      graphicsCard: decodeGraphicsCard(ocr.nullableObject('gpu')),
    },
    queue: {
      queuedCount: queue.number('queued'),
      processingCount: queue.number('processing'),
      errorCount: queue.number('error'),
      doneCount: queue.number('done'),
    },
    libraryDirectory: status.string('library_dir'),
  };
};
