// Builds the web UI into the tree that the api serves: index.html, which names the hashed script and stylesheet, and
// static/, which holds them under assets/, beside the icons and the manifest, whose URLs stay stable.
//
// Usage: node build.ts --outdir DIR
import { cpSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

import { build, type Metafile } from 'esbuild';

export interface BuiltFiles {
  readonly script: string;
  readonly stylesheet: string;
}

const WEB_DIRECTORY = fileURLToPath(new URL('./', import.meta.url));
const ENTRY_POINT = 'src/main.tsx';
const PAGE_TEMPLATE = 'src/index.html';
const STATIC_DIRECTORY = 'static';
const PUBLIC_PATH = '/static/';
// Only the build writes under assets/, and every name there carries a hash of its content, which lets the api serve
// them as immutable.
const HASHED_NAMES = 'assets/[name]-[hash]';
const STABLE_FILES = ['icons', 'manifest.webmanifest'];
const STYLESHEET_MARKER = '<!-- stylesheet -->';
const SCRIPT_MARKER = '<!-- script -->';

function replaceMarker(page: string, marker: string, element: string): string {
  const parts = page.split(marker);
  if (parts.length !== 2) {
    throw new Error(`The page template must hold ${marker} exactly once, not ${parts.length - 1} times`);
  }
  return parts.join(element);
}

export function writeEntryPage(template: string, files: BuiltFiles): string {
  const stylesheet = `<link rel="stylesheet" href="${PUBLIC_PATH}${files.stylesheet}">`;
  const script = `<script type="module" src="${PUBLIC_PATH}${files.script}"></script>`;
  return replaceMarker(replaceMarker(template, STYLESHEET_MARKER, stylesheet), SCRIPT_MARKER, script);
}

// The metafile names each output relative to the working directory, and the entry page names them relative to static/.
export function findBuiltFiles(metafile: Metafile, entryPoint: string, staticFromWorkingDirectory: string): BuiltFiles {
  const entryOutputs = Object.entries(metafile.outputs).filter(([, output]) => output.entryPoint === entryPoint);
  const [entryOutput, ...otherOutputs] = entryOutputs;
  if (entryOutput === undefined || otherOutputs.length > 0) {
    throw new Error(`The build must write one script for ${entryPoint}, not ${entryOutputs.length}`);
  }
  const [scriptPath, { cssBundle }] = entryOutput;
  if (cssBundle === undefined) throw new Error(`The build wrote no stylesheet for ${entryPoint}`);
  return {
    script: relative(staticFromWorkingDirectory, scriptPath),
    stylesheet: relative(staticFromWorkingDirectory, cssBundle),
  };
}

async function buildWebUi(outputDirectory: string): Promise<void> {
  const staticDirectory = join(outputDirectory, STATIC_DIRECTORY);
  const { metafile } = await build({
    absWorkingDir: WEB_DIRECTORY,
    entryPoints: [ENTRY_POINT],
    outdir: staticDirectory,
    bundle: true,
    format: 'esm',
    minify: true,
    jsx: 'automatic',
    define: { 'process.env.NODE_ENV': '"production"' },
    loader: { '.woff2': 'file', '.woff': 'file', '.ttf': 'file' },
    entryNames: HASHED_NAMES,
    assetNames: HASHED_NAMES,
    chunkNames: HASHED_NAMES,
    publicPath: PUBLIC_PATH,
    legalComments: 'eof',
    metafile: true,
  });
  const files = findBuiltFiles(metafile, ENTRY_POINT, relative(WEB_DIRECTORY, staticDirectory));
  for (const file of [files.script, files.stylesheet]) {
    if (!existsSync(join(staticDirectory, file))) throw new Error(`The build did not write ${file}`);
  }
  const template = readFileSync(join(WEB_DIRECTORY, PAGE_TEMPLATE), 'utf8');
  writeFileSync(join(outputDirectory, 'index.html'), writeEntryPage(template, files));
  for (const file of STABLE_FILES) {
    cpSync(join(WEB_DIRECTORY, STATIC_DIRECTORY, file), join(staticDirectory, file), { recursive: true });
  }
}

if (import.meta.main) {
  const { values } = parseArgs({ options: { outdir: { type: 'string' } } });
  if (values.outdir === undefined) throw new Error('Usage: node build.ts --outdir DIR');
  await buildWebUi(resolve(values.outdir));
}
