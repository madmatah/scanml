import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';
import { after, before, describe, it } from 'node:test';

interface Sample {
  readonly situation: string;
  readonly path: string;
  readonly source: string;
}

interface BreakingSample extends Sample {
  readonly finding: string;
}

interface PluginSamples {
  readonly plugin: string;
  readonly breaking: readonly BreakingSample[];
  readonly keeping: readonly Sample[];
}

interface Finding {
  readonly category: string;
  readonly severity: string;
  readonly message: string;
}

const BIOME = createRequire(import.meta.url).resolve('@biomejs/biome/bin/biome');
// Biome exits with 1 when it reports an error, and its report is then as complete as with 0.
const REPORTED_STATUSES = new Set([0, 1]);

const HOOK_IN_COMPONENT =
  'Call this hook in a hook of a use-*.ts file, not in a component, which only renders what it is given.';
const WHOLE_PACKAGE_IMPORT = "Import this package's names one by one, not as a default or namespace import.";

const PLUGINS: readonly PluginSamples[] = [
  {
    plugin: 'arrow-functions',
    breaking: [
      {
        situation: 'When a function is declared with the function keyword',
        finding: 'Declare this function as a const arrow function.',
        path: 'breaks-arrow-functions.ts',
        source: 'export function pageCount(): number {\n  return 1;\n}\n',
      },
    ],
    keeping: [
      {
        situation: 'When a function is declared as a const arrow function',
        path: 'keeps-arrow-functions.ts',
        source: 'export const pageCount = (): number => 1;\n',
      },
    ],
  },
  {
    plugin: 'typed-components',
    breaking: [
      {
        situation: 'When a component is left untyped',
        finding: 'Type this component as FC<Props>.',
        path: 'breaks-typed-components.tsx',
        source: 'export const Divider = () => <hr />;\n',
      },
    ],
    keeping: [
      {
        situation: 'When a component is typed as FC',
        path: 'keeps-typed-components.tsx',
        source: "import type { FC } from 'react';\n\nexport const Divider: FC = () => <hr />;\n",
      },
    ],
  },
  {
    plugin: 'stateless-components',
    breaking: [
      {
        situation: 'When a component imports a hook by its name',
        finding: HOOK_IN_COMPONENT,
        path: 'breaks-stateless-components-by-name.tsx',
        source:
          "import { type FC, useState } from 'react';\n\n" +
          'export const PageCount: FC = () => {\n  const [count] = useState(0);\n  return <output>{count}</output>;\n};\n',
      },
      {
        situation: 'When a component imports a hook under a name that hides it',
        finding: HOOK_IN_COMPONENT,
        path: 'breaks-stateless-components-under-alias.tsx',
        source:
          "import { type FC, useState as keepCount } from 'react';\n\n" +
          'export const PageCount: FC = () => {\n  const [count] = keepCount(0);\n  return <output>{count}</output>;\n};\n',
      },
      {
        situation: 'When a component imports a hook that React Router prefixes as unstable',
        finding: HOOK_IN_COMPONENT,
        path: 'breaks-stateless-components-unstable.tsx',
        source:
          "import type { FC } from 'react';\nimport { unstable_usePrompt } from 'react-router';\n\n" +
          "export const PageCount: FC = () => {\n  unstable_usePrompt({ when: true, message: 'Leave?' });\n" +
          '  return <output />;\n};\n',
      },
      {
        situation: 'When a component imports React as a default import',
        finding: WHOLE_PACKAGE_IMPORT,
        path: 'breaks-stateless-components-default.tsx',
        source:
          "import React from 'react';\n\n" +
          'export const PageCount: React.FC = () => {\n  const [count] = React.useState(0);\n' +
          '  return <output>{count}</output>;\n};\n',
      },
      {
        situation: 'When a component imports React as a namespace',
        finding: WHOLE_PACKAGE_IMPORT,
        path: 'breaks-stateless-components-namespace.tsx',
        source:
          "import * as React from 'react';\n\n" +
          'export const PageCount: React.FC = () => {\n  const [count] = React.useState(0);\n' +
          '  return <output>{count}</output>;\n};\n',
      },
    ],
    keeping: [
      {
        situation: 'When a component imports useId',
        path: 'keeps-stateless-components-use-id.tsx',
        source:
          "import { type FC, useId } from 'react';\n\n" +
          'export const PageCount: FC = () => {\n  const id = useId();\n  return <output id={id} />;\n};\n',
      },
      {
        situation: 'When a component imports useRef',
        path: 'keeps-stateless-components-use-ref.tsx',
        source:
          "import { type FC, useRef } from 'react';\n\n" +
          'export const PageCount: FC = () => {\n  const output = useRef<HTMLOutputElement>(null);\n' +
          '  return <output ref={output} />;\n};\n',
      },
      {
        situation: 'When a component imports a hook of another package',
        path: 'keeps-stateless-components-other-package.tsx',
        source:
          "import type { FC } from 'react';\nimport { useTranslation } from 'react-i18next';\n\n" +
          'export const PageCount: FC = () => {\n  const { i18n } = useTranslation();\n' +
          '  return <output lang={i18n.language} />;\n};\n',
      },
    ],
  },
];
const SAMPLES = PLUGINS.flatMap(({ breaking, keeping }) => [...breaking, ...keeping]);

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

  for (const { plugin, breaking, keeping } of PLUGINS) {
    describe(`The ${plugin} plugin`, () => {
      describe('When a sample breaks its rule', () => {
        for (const { situation, path, finding } of breaking) {
          describe(situation, () => {
            it('should report its finding alone, so that a plugin that errors, which Biome reports as an info, fails', () => {
              assert.deepEqual(findingsBySample.get(path), [
                { category: 'plugin', severity: 'error', message: finding },
              ]);
            });
          });
        }
      });

      describe('When a sample keeps its rule', () => {
        for (const { situation, path } of keeping) {
          describe(situation, () => {
            it('should report nothing', () => {
              assert.deepEqual(findingsBySample.get(path) ?? [], []);
            });
          });
        }
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
