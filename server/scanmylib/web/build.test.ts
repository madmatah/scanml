import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import type { Metafile } from 'esbuild';

import { type BuiltFiles, findBuiltFiles, writeEntryPage } from './build.ts';

const FILES: BuiltFiles = { script: 'assets/main-ABCD1234.js', stylesheet: 'assets/main-EFGH5678.css' };
const STYLESHEET_MARKER = '<!-- stylesheet -->';
const SCRIPT_MARKER = '<!-- script -->';
const ENTRY_POINT = 'src/main.tsx';
const STATIC_DIRECTORY = '../../tmp/build/static';

type Output = Metafile['outputs'][string];

function output(fields: Partial<Output> = {}): Output {
  return { bytes: 1, inputs: {}, imports: [], exports: [], ...fields };
}

function metafileOf(outputs: Record<string, Output>): Metafile {
  return { inputs: {}, outputs };
}

describe('The build', () => {
  describe('The writeEntryPage() function', () => {
    describe('When the template holds each marker once', () => {
      const template = `<head>\n  ${STYLESHEET_MARKER}\n  ${SCRIPT_MARKER}\n</head>`;
      let page: string;
      beforeEach(() => {
        page = writeEntryPage(template, FILES);
      });

      it('should name the hashed stylesheet and module script under the static files, in place of the markers', () => {
        assert.equal(
          page,
          '<head>\n' +
            '  <link rel="stylesheet" href="/static/assets/main-EFGH5678.css">\n' +
            '  <script type="module" src="/static/assets/main-ABCD1234.js"></script>\n' +
            '</head>',
        );
      });
    });

    const brokenTemplates = [
      {
        situation: 'When the template lacks the marker of the stylesheet',
        template: `<head>${SCRIPT_MARKER}</head>`,
        rule: 'should fail, naming the marker and its count',
        expectedMessage: /must hold <!-- stylesheet --> exactly once, not 0 times/,
      },
      {
        situation: 'When the template holds the marker of the script twice',
        template: `<head>${STYLESHEET_MARKER}${SCRIPT_MARKER}${SCRIPT_MARKER}</head>`,
        rule: 'should fail, naming the marker and its count',
        expectedMessage: /must hold <!-- script --> exactly once, not 2 times/,
      },
    ];

    for (const { situation, template, rule, expectedMessage } of brokenTemplates) {
      describe(situation, () => {
        let act: () => string;
        beforeEach(() => {
          act = () => writeEntryPage(template, FILES);
        });

        it(rule, () => {
          assert.throws(act, { name: 'Error', message: expectedMessage });
        });
      });
    }
  });

  describe('The findBuiltFiles() function', () => {
    describe('When the entry point has its script and its stylesheet', () => {
      const metafile = metafileOf({
        [`${STATIC_DIRECTORY}/assets/main-ABCD1234.js`]: output({
          entryPoint: ENTRY_POINT,
          cssBundle: `${STATIC_DIRECTORY}/assets/main-EFGH5678.css`,
        }),
        [`${STATIC_DIRECTORY}/assets/main-EFGH5678.css`]: output(),
        [`${STATIC_DIRECTORY}/assets/font-IJKL9012.woff2`]: output(),
      });
      let files: BuiltFiles;
      beforeEach(() => {
        files = findBuiltFiles(metafile, ENTRY_POINT, STATIC_DIRECTORY);
      });

      it('should give both, relative to the static files', () => {
        assert.deepEqual(files, FILES);
      });
    });

    const brokenBuilds = [
      {
        situation: 'When the entry point has no stylesheet',
        metafile: metafileOf({ [`${STATIC_DIRECTORY}/assets/main-ABCD1234.js`]: output({ entryPoint: ENTRY_POINT }) }),
        rule: 'should fail, since the page would show without its styles',
        expectedMessage: /wrote no stylesheet for src\/main.tsx/,
      },
      {
        situation: 'When no output comes from the entry point',
        metafile: metafileOf({
          [`${STATIC_DIRECTORY}/assets/other-ABCD1234.js`]: output({ entryPoint: 'src/other.ts' }),
        }),
        rule: 'should fail, naming the count of its scripts',
        expectedMessage: /must write one script for src\/main.tsx, not 0/,
      },
    ];

    for (const { situation, metafile, rule, expectedMessage } of brokenBuilds) {
      describe(situation, () => {
        let act: () => BuiltFiles;
        beforeEach(() => {
          act = () => findBuiltFiles(metafile, ENTRY_POINT, STATIC_DIRECTORY);
        });

        it(rule, () => {
          assert.throws(act, { name: 'Error', message: expectedMessage });
        });
      });
    }
  });
});
