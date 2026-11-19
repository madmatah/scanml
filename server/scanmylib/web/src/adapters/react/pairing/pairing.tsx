import { type FC, useEffect, useRef, useState } from 'react';
import { Trans, useTranslation } from 'react-i18next';

import type { Clipboard } from '../../../application/clipboard.ts';
import type { PairingSource } from '../../../application/pairing-source.ts';
import type { PairingDetails } from '../../../domain/pairing-details.ts';
import { quoted } from '../../i18next/formatted-text.ts';
import { errorMessage } from '../shell/error-message.ts';
import { ErrorState } from '../shell/error-state.tsx';
import { Icon } from '../shell/icon.tsx';
import { LoadingState } from '../shell/loading-state.tsx';
import type { Toasts } from '../shell/toasts.ts';
import { useDocumentTitle } from '../shell/use-document-title.ts';
import { CopyField } from './copy-field.tsx';
import { QrCode } from './qr-code.tsx';

const APK_FILE_NAME = 'scanmylib.apk';
const ANDROID_FOLDER = 'android/';

type PairingLoad =
  | { readonly phase: 'loading' }
  | { readonly phase: 'failed'; readonly failure: unknown }
  | { readonly phase: 'loaded'; readonly pairing: PairingDetails };

export interface PairingProps {
  readonly source: PairingSource;
  readonly clipboard: Clipboard;
  readonly toasts: Toasts;
}

export const Pairing: FC<PairingProps> = ({ source, clipboard, toasts }) => {
  const { t } = useTranslation();
  const [load, setLoad] = useState<PairingLoad>({ phase: 'loading' });
  const reload = useRef<() => void>(() => {});
  useDocumentTitle(t('Pairing'));

  useEffect(() => {
    const leaving = new AbortController();
    const loadPairing = async (): Promise<void> => {
      setLoad({ phase: 'loading' });
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

  return (
    <section className="view pairing">
      <header className="view-header">
        <div className="view-heading">
          <h1 tabIndex={-1}>{t('Pair the phone')}</h1>
          <p className="view-subtitle">{t('Two steps: install the Android app, then pair it with this PC.')}</p>
        </div>
      </header>
      <div className="pairing-content">
        {load.phase === 'loading' && <LoadingState />}
        {load.phase === 'failed' && (
          <ErrorState message={errorMessage(t, load.failure)} onRetry={() => reload.current()} />
        )}
        {load.phase === 'loaded' && (
          <div className="pairing-grid">
            <InstallCard pairing={load.pairing} source={source} />
            <PairCard pairing={load.pairing} source={source} clipboard={clipboard} toasts={toasts} />
          </div>
        )}
      </div>
    </section>
  );
};

interface InstallCardProps {
  readonly pairing: PairingDetails;
  readonly source: PairingSource;
}

const InstallCard: FC<InstallCardProps> = ({ pairing, source }) => {
  const { t } = useTranslation();
  return (
    <section className="card pairing-step" aria-labelledby="install-title">
      <h2 id="install-title" className="card-title">
        <span className="step-number" aria-hidden="true">
          1
        </span>
        {t('Install the Android app')}
      </h2>
      {pairing.isApkAvailable ? (
        <>
          <QrCode url={source.apkQrCodeUrl} description={t('QR code of the Android app’s download link')} />
          <ol className="steps">
            <li>
              <Trans
                t={t}
                i18nKey="Scan this QR code with the phone’s camera to download <fileName>{{file}}</fileName>."
                values={{ file: APK_FILE_NAME }}
                components={{ fileName: <strong /> }}
              />
            </li>
            <li>
              <Trans
                t={t}
                i18nKey="Open the downloaded file. The first time, Android blocks the installation: tap <settingsName>{{settings}}</settingsName> and allow installing unknown apps ({{unknownSources}}) <browserOnly>{{thisBrowserOnly}}</browserOnly>, then go back and tap <installName>{{install}}</installName>."
                values={{
                  settings: t('Settings'),
                  unknownSources: quoted(t, t('unknown sources')),
                  thisBrowserOnly: t('for this browser only'),
                  install: t('Install'),
                }}
                components={{ settingsName: <strong />, browserOnly: <strong />, installName: <strong /> }}
              />
            </li>
            <li>{t('Play Protect may report an unknown app: this is normal for an APK built on your PC.')}</li>
          </ol>
          <div className="button-row">
            <a className="btn" href={source.apkDownloadUrl} download={APK_FILE_NAME}>
              <Icon name="download" />
              {t('Download the APK')}
            </a>
          </div>
          <p className="hint">
            <Trans
              t={t}
              i18nKey="Download address: <downloadUrl>{{url}}</downloadUrl>"
              values={{ url: pairing.apkUrl }}
              components={{ downloadUrl: <code className="path" /> }}
            />
          </p>
        </>
      ) : (
        <div className="notice">
          <Icon name="alert" />
          <p>
            <strong>{t('The APK is not available yet.')}</strong>{' '}
            <Trans
              t={t}
              i18nKey="Build the Android app (the project’s <folderName>{{folder}}</folderName> folder), then reload this page."
              values={{ folder: ANDROID_FOLDER }}
              components={{ folderName: <code /> }}
            />
          </p>
        </div>
      )}
    </section>
  );
};

interface PairCardProps {
  readonly pairing: PairingDetails;
  readonly source: PairingSource;
  readonly clipboard: Clipboard;
  readonly toasts: Toasts;
}

// The labels quoted here are those of the Android app's pairing screen.
const PairCard: FC<PairCardProps> = ({ pairing, source, clipboard, toasts }) => {
  const { t } = useTranslation();
  return (
    <section className="card pairing-step" aria-labelledby="pair-title">
      <h2 id="pair-title" className="card-title">
        <span className="step-number" aria-hidden="true">
          2
        </span>
        {t('Pair the app with this PC')}
      </h2>
      <QrCode url={source.pairingQrCodeUrl} description={t('Pairing QR code: address of this PC and access token')} />
      <ol className="steps">
        <li>
          <Trans
            t={t}
            i18nKey="Open ScanMyLib on the phone: on the {{screen}} screen, tap <buttonName>{{button}}</buttonName>."
            values={{ screen: quoted(t, t('Pair with PC')), button: t('Scan the QR code') }}
            components={{ buttonName: <strong /> }}
          />
        </li>
        <li>{t('Point the phone at this QR code: the app saves the PC address and the access token.')}</li>
        <li>{t('The phone must be on the same Wi-Fi network as this PC (or connected through a VPN).')}</li>
      </ol>
      <div className="notice notice-warn">
        <Icon name="alert" />
        <p>{t('This QR code and this token give access to your library: do not share them.')}</p>
      </div>
      <h3 className="subsection-title">{t('Manual entry')}</h3>
      <p className="hint">
        {t('Without a QR code reader, copy these two values into the app, then tap {{button}}.', {
          button: quoted(t, t('Test and pair')),
        })}
      </p>
      <CopyField
        label={t('PC address')}
        text={pairing.serverUrl}
        isSecret={false}
        copiedMessage={t('Address copied.')}
        clipboard={clipboard}
        toasts={toasts}
      />
      <CopyField
        label={t('Access token')}
        text={pairing.accessToken}
        isSecret
        copiedMessage={t('Access token copied.')}
        clipboard={clipboard}
        toasts={toasts}
      />
    </section>
  );
};
