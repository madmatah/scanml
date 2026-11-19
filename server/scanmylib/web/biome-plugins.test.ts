import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';
import { after, before, describe, it } from 'node:test';

interface Sample {
  readonly path: string;
  readonly source: string;
}

interface PluginSamples {
  readonly plugin: string;
  readonly finding: string;
  readonly breaking: Sample;
  readonly keeping: Sample;
}

interface Finding {
  readonly category: string;
  readonly severity: string;
  readonly message: string;
}

const BIOME = createRequire(import.meta.url).resolve('@biomejs/biome/bin/biome');
// Biome exits with 1 when it reports an error, and its report is then as complete as with 0.
const REPORTED_STATUSES = new Set([0, 1]);

const PLUGINS: readonly PluginSamples[] = [
  {
    plugin: 'arrow-functions',
    finding: 'Declare this function as a const arrow function.',
    breaking: {
      path: 'breaks-arrow-functions.ts',
      source: 'export function pageCount(): number {\n  return 1;\n}\n',
    },
    keeping: {
      path: 'keeps-arrow-functions.ts',
      source: 'export const pageCount = (): number => 1;\n',
    },
  },
  {
    plugin: 'typed-components',
    finding: 'Type this component as FC<Props>.',
    breaking: {
      path: 'breaks-typed-components.tsx',
      source: 'export const Divider = () => <hr />;\n',
    },
    keeping: {
      path: 'keeps-typed-components.tsx',
      source: "import type { FC } from 'react';\n\nexport const Divider: FC = () => <hr />;\n",
    },
  },
];
const SAMPLES = PLUGINS.flatMap(({ breaking, keeping }) => [breaking, keeping]);

const isRecord = (candidate: unknown): candidate is Record<string, unknown> => {
  return typeof candidate === 'object' && candidate !== null;
};

// The web UI's configuration and plugins, copied beside the samples, since the gate mounts the web UI read-only.
const writeProject = (samples: readonly Sample[]): string => {
  const project = mkdtempSync(join(tmpdir(), 'biome-plugins-'));
  cpSync(join(import.meta.dirname, 'biome.json'), join(project, 'biome.json'));
  cpSync(join(import.meta.dirname, 'biome-plugins'), join(project, 'biome-plugins'), { recursive: true });
  for (const { path, source } of samples) {
    writeFileSync(join(project, path), source);
  }
  return project;
};

const lint = (project: string, samples: readonly Sample[]): unknown => {
  const paths = samples.map(({ path }) => path);
  const run = spawnSync(
    process.execPath,
    [BIOME, 'lint', '--colors=off', '--reporter=json', '--max-diagnostics=none', ...paths],
    { cwd: project, encoding: 'utf8' },
  );
  if (run.status === null || !REPORTED_STATUSES.has(run.status)) {
    throw new Error(`Biome failed with the status ${run.status}: ${run.error ?? run.stderr}`);
  }
  return JSON.parse(run.stdout);
};

const sampleFindingOf = (diagnostic: unknown): [string, Finding] => {
  if (!isRecord(diagnostic) || !isRecord(diagnostic.location)) {
    throw new Error(`Biome's report holds a diagnostic of an unknown shape: ${JSON.stringify(diagnostic)}`);
  }
  const { category, severity, message } = diagnostic;
  const { path } = diagnostic.location;
  if (typeof category !== 'string' || typeof severity !== 'string' || typeof message !== 'string') {
    throw new Error(`Biome's report holds a diagnostic of an unknown shape: ${JSON.stringify(diagnostic)}`);
  }
  if (typeof path !== 'string') {
    throw new Error(`Biome's report holds a diagnostic without a path: ${JSON.stringify(diagnostic)}`);
  }
  return [path, { category, severity, message }];
};

const findingsBySampleOf = (report: unknown): Map<string, Finding[]> => {
  if (!isRecord(report) || !Array.isArray(report.diagnostics)) {
    throw new Error(`Biome's report has an unknown shape: ${JSON.stringify(report)}`);
  }
  const findingsBySample = new Map<string, Finding[]>();
  for (const [path, finding] of report.diagnostics.map(sampleFindingOf)) {
    findingsBySample.set(path, [...(findingsBySample.get(path) ?? []), finding]);
  }
  return findingsBySample;
};

const configuredPluginsOf = (configuration: unknown): string[] => {
  if (!isRecord(configuration) || !Array.isArray(configuration.plugins)) {
    throw new Error(`Biome's configuration has an unknown shape: ${JSON.stringify(configuration)}`);
  }
  return configuration.plugins.map((entry: unknown) => {
    const path = isRecord(entry) ? entry.path : entry;
    if (typeof path !== 'string') {
      throw new Error(`Biome's configuration names a plugin without a path: ${JSON.stringify(entry)}`);
    }
    return basename(path, '.grit');
  });
};

describe('The Biome plugins', () => {
  let project: string;
  let findingsBySample: Map<string, Finding[]>;
  before(() => {
    project = writeProject(SAMPLES);
    findingsBySample = findingsBySampleOf(lint(project, SAMPLES));
  });
  after(() => {
    rmSync(project, { recursive: true, force: true });
  });

  for (const { plugin, finding, breaking, keeping } of PLUGINS) {
    describe(`The ${plugin} plugin`, () => {
      describe('When a sample breaks its rule', () => {
        it('should report its finding alone, so that a plugin that errors, which Biome reports as an info, fails', () => {
          assert.deepEqual(findingsBySample.get(breaking.path), [
            { category: 'plugin', severity: 'error', message: finding },
          ]);
        });
      });

      describe('When a sample keeps its rule', () => {
        it('should report nothing', () => {
          assert.deepEqual(findingsBySample.get(keeping.path) ?? [], []);
        });
      });
    });
  }

  describe('When the configuration names its plugins', () => {
    let configuredPlugins: string[];
    before(() => {
      const configurationText = readFileSync(join(import.meta.dirname, 'biome.json'), 'utf8');
      configuredPlugins = configuredPluginsOf(JSON.parse(configurationText));
    });

    it('should name only the plugins under test, so that a plugin added later cannot escape this test', () => {
      assert.deepEqual(configuredPlugins.toSorted(), PLUGINS.map(({ plugin }) => plugin).toSorted());
    });
  });
});
