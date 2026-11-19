import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Clipboard } from '../../../application/clipboard.ts';
import type { PairingSource } from '../../../application/pairing-source.ts';
import type { PairingDetails } from '../../../domain/pairing-details.ts';
import type { Toasts } from '../shell/toasts.ts';
import { useDocumentTitle } from '../shell/use-document-title.ts';

type PairingLoad =
  | { readonly phase: 'loading' }
  | { readonly phase: 'failed'; readonly failure: unknown }
  | { readonly phase: 'loaded'; readonly pairing: PairingDetails };

export type PairingQrCode = 'install' | 'pair';

export interface PairingScreenState {
  readonly load: PairingLoad;
  readonly isTokenShown: boolean;
  readonly missingQrCodes: ReadonlySet<PairingQrCode>;
  readonly onRetry: () => void;
  readonly onToggleToken: () => void;
  readonly onCopy: (text: string, copiedMessage: string) => void;
  readonly onQrCodeMissing: (qrCode: PairingQrCode) => void;
}

const NO_MISSING_QR_CODES: ReadonlySet<PairingQrCode> = new Set();

export const usePairingScreen = (source: PairingSource, clipboard: Clipboard, toasts: Toasts): PairingScreenState => {
  const { t } = useTranslation();
  const [load, setLoad] = useState<PairingLoad>({ phase: 'loading' });
  const [isTokenShown, setTokenShown] = useState(false);
  const [missingQrCodes, setMissingQrCodes] = useState(NO_MISSING_QR_CODES);
  const reload = useRef<() => void>(() => {});
  useDocumentTitle(t('Pairing'));

  useEffect(() => {
    const leaving = new AbortController();
    const loadPairing = async (): Promise<void> => {
      setLoad({ phase: 'loading' });
      // The QR codes and the token field are drawn again by each load, hidden and not yet missing.
      setTokenShown(false);
      setMissingQrCodes(NO_MISSING_QR_CODES);
      try {
        setLoad({ phase: 'loaded', pairing: await source.readPairing(leaving.signal) });
      } catch (failure) {
        if (!leaving.signal.aborted) setLoad({ phase: 'failed', failure });
      }
    };
    const loadAgain = (): void => {
      // loadPairing handles its own failures, so its promise never rejects.
      void loadPairing();
    };
    reload.current = loadAgain;
    loadAgain();
    return () => leaving.abort();
  }, [source]);

  const copy = async (text: string, copiedMessage: string): Promise<void> => {
    if (await clipboard.copyText(text)) toasts.show(copiedMessage, 'success');
    else toasts.show(t('Could not copy: select the text by hand.'), 'error');
  };

  return {
    load,
    isTokenShown,
    missingQrCodes,
    onRetry: () => reload.current(),
    onToggleToken: () => setTokenShown(!isTokenShown),
    onCopy: (text, copiedMessage) => {
      // copy tells its outcome in a toast, and the clipboard's copy never rejects.
      void copy(text, copiedMessage);
    },
    onQrCodeMissing: (qrCode) => setMissingQrCodes((missing) => new Set(missing).add(qrCode)),
  };
};
