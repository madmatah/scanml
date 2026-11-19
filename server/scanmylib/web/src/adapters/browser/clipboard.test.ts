import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { type ClipboardApis, createClipboard } from './clipboard.ts';

const TEXT = 'http://192.168.1.10:8765';

interface Copies {
  readonly written: string[];
  readonly commanded: string[];
}

interface ApisChoice {
  readonly isSecureContext: boolean;
  readonly hasClipboardApi: boolean;
  readonly isWriteRefused: boolean;
  readonly isCommandRefused: boolean;
}

function fakeApis(choice: ApisChoice, copies: Copies): ClipboardApis {
  return {
    isSecureContext: choice.isSecureContext,
    writeText: choice.hasClipboardApi
      ? async (text) => {
          if (choice.isWriteRefused) throw new Error('Write permission denied.');
          copies.written.push(text);
        }
      : null,
    copyWithCommand: (text) => {
      if (choice.isCommandRefused) return false;
      copies.commanded.push(text);
      return true;
    },
  };
}

describe('The clipboard', () => {
  describe('The copyText() function', () => {
    const situations: {
      situation: string;
      choice: ApisChoice;
      rule: string;
      expected: { isCopied: boolean; written: string[]; commanded: string[] };
    }[] = [
      {
        situation: 'When the page is in a secure context',
        choice: { isSecureContext: true, hasClipboardApi: true, isWriteRefused: false, isCommandRefused: false },
        rule: 'should copy through the Clipboard API alone',
        expected: { isCopied: true, written: [TEXT], commanded: [] },
      },
      {
        situation: 'When the page is opened over plain HTTP',
        choice: { isSecureContext: false, hasClipboardApi: false, isWriteRefused: false, isCommandRefused: false },
        rule: 'should copy through the copy command',
        expected: { isCopied: true, written: [], commanded: [TEXT] },
      },
      {
        situation: 'When the Clipboard API refuses the copy',
        choice: { isSecureContext: true, hasClipboardApi: true, isWriteRefused: true, isCommandRefused: false },
        rule: 'should try the copy command',
        expected: { isCopied: true, written: [], commanded: [TEXT] },
      },
      {
        situation: 'When the copy command fails too',
        choice: { isSecureContext: false, hasClipboardApi: false, isWriteRefused: false, isCommandRefused: true },
        rule: 'should say that nothing was copied, so that the user selects the text by hand',
        expected: { isCopied: false, written: [], commanded: [] },
      },
    ];

    for (const { situation, choice, rule, expected } of situations) {
      describe(situation, () => {
        let copies: Copies;
        let isCopied: boolean;
        beforeEach(async () => {
          copies = { written: [], commanded: [] };
          isCopied = await createClipboard(fakeApis(choice, copies)).copyText(TEXT);
        });

        it(rule, () => {
          assert.deepEqual({ isCopied, ...copies }, expected);
        });
      });
    }
  });
});
