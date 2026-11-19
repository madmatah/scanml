import type { FC } from 'react';
import { useTranslation } from 'react-i18next';

const QR_CODE_PIXELS = 220;

export interface QrCodeProps {
  readonly url: string;
  readonly description: string;
  readonly isMissing: boolean;
  readonly onMissing: () => void;
}

// In a white frame, since a QR code needs a light quiet zone around it, in the dark theme too.
export const QrCode: FC<QrCodeProps> = ({ url, description, isMissing, onMissing }) => {
  const { t } = useTranslation();
  return (
    <div className="qr-frame">
      {isMissing ? (
        <p className="qr-missing">{t('QR code unavailable.')}</p>
      ) : (
        <img src={url} alt={description} width={QR_CODE_PIXELS} height={QR_CODE_PIXELS} onError={onMissing} />
      )}
    </div>
  );
};
