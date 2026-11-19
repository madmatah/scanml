import type { Clock, PageUpload, PageUploader, PhotoFile } from './upload-queue.ts';
import type { UuidSource } from './uuid-source.ts';

export interface StartedUpload {
  readonly upload: PageUpload<PhotoFile>;
  readonly reportProgress: (ratio: number) => void;
  readonly succeed: () => Promise<void>;
  readonly fail: (failure: Error) => Promise<void>;
}

export interface FakePageUploader extends PageUploader<PhotoFile> {
  readonly started: StartedUpload[];
  readonly startedOf: (pageId: string) => StartedUpload;
}

const settle = (): Promise<void> => {
  return new Promise((resolve) => {
    setImmediate(resolve);
  });
};

export const createFakePageUploader = (): FakePageUploader => {
  const started: StartedUpload[] = [];
  return {
    started,
    startedOf(pageId) {
      const found = started.findLast((candidate) => candidate.upload.pageId === pageId);
      if (found === undefined) throw new Error(`No upload of the page ${pageId} has started`);
      return found;
    },
    uploadPage(upload, onProgress) {
      return new Promise((resolve, reject) => {
        started.push({
          upload,
          reportProgress: onProgress,
          succeed: async () => {
            resolve();
            await settle();
          },
          fail: async (failure) => {
            reject(failure);
            await settle();
          },
        });
      });
    },
  };
};

// Page ids that tell in which order they were made.
export const createCountingUuidSource = (): UuidSource => {
  let count = 0;
  return {
    createUuid() {
      count += 1;
      return `00000000-0000-4000-8000-${String(count).padStart(12, '0')}`;
    },
  };
};

export const createFixedClock = (nowMilliseconds: number): Clock => {
  return { readTimeMilliseconds: () => nowMilliseconds };
};

export const photo = (name: string, overrides: Partial<PhotoFile> = {}): PhotoFile => {
  return { name, size: 1000, type: 'image/jpeg', lastModified: Date.UTC(2026, 2, 7, 9, 5, 3), ...overrides };
};
