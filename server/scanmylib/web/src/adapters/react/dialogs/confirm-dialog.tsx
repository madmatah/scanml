import { type FC, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';

import { useModal } from './use-modal.ts';

export interface ConfirmDialogProps {
  readonly title: string;
  readonly message?: string;
  readonly confirmLabel: string;
  readonly isDanger?: boolean;
  readonly onClosed: (isConfirmed: boolean) => void;
}

const CONFIRM = 'confirm';

export const ConfirmDialog: FC<ConfirmDialogProps> = ({ title, message, confirmLabel, isDanger = false, onClosed }) => {
  const { t } = useTranslation();
  const titleId = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  // Cancel has the focus, so that Enter never confirms by accident.
  const returnFocus = useModal(dialog, cancelButton);

  return createPortal(
    <dialog
      ref={dialog}
      className="dialog"
      aria-labelledby={titleId}
      onClose={() => {
        returnFocus();
        onClosed(dialog.current?.returnValue === CONFIRM);
      }}
    >
      <form method="dialog" className="dialog-body">
        <h2 id={titleId} className="dialog-title">
          {title}
        </h2>
        {message !== undefined && message !== '' && <p className="dialog-text">{message}</p>}
        <div className="dialog-actions">
          <button ref={cancelButton} type="submit" value="cancel" className="btn">
            {t('Cancel')}
          </button>
          <button type="submit" value={CONFIRM} className={isDanger ? 'btn btn-danger-solid' : 'btn btn-primary'}>
            {confirmLabel}
          </button>
        </div>
      </form>
    </dialog>,
    document.body,
  );
};
