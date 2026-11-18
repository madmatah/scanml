import { useState } from 'react';
import { useTranslation } from 'react-i18next';

const QR_CODE_PIXELS = 220;

export interface QrCodeProps {
  readonly url: string;
  readonly description: string;
}

// In a white frame, since a QR code needs a light quiet zone around it, in the dark theme too.
export function QrCode({ url, description }: QrCodeProps) {
  const { t } = useTranslation();
  const [isMissing, setMissing] = useState(false);
  return (
    <div className="qr-frame">
      {isMissing ? (
        <p className="qr-missing">{t('QR code unavailable.')}</p>
      ) : (
        <img
          src={url}
          alt={description}
          width={QR_CODE_PIXELS}
          height={QR_CODE_PIXELS}
          onError={() => setMissing(true)}
        />
      )}
    </div>
  );
}
