import { useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';

import type { PageId, Side } from '../../../domain/reading-order.ts';
import { useModal } from '../dialogs/use-modal.ts';
import { Icon } from '../shell/icon.tsx';
import { type MoveChoice, moveSummaryText, selectedPagesText } from './organizer-text.ts';

export interface MoveTarget {
  readonly targetId: PageId;
  readonly side: Side;
}

export interface MoveDialogProps {
  readonly count: number;
  readonly choices: readonly MoveChoice[];
  readonly onClosed: (target: MoveTarget | null) => void;
}

const MOVE = 'move';
const SIDES: readonly Side[] = ['before', 'after'];

export const MoveDialog = ({ count, choices, onClosed }: MoveDialogProps) => {
  const { t } = useTranslation();
  const ids = { title: useId(), target: useId(), summary: useId() };
  const dialog = useRef<HTMLDialogElement>(null);
  const targetSelect = useRef<HTMLSelectElement>(null);
  const [side, setSide] = useState<Side>('before');
  const [targetId, setTargetId] = useState<PageId>(choices[0]?.pageId ?? '');
  const returnFocus = useModal(dialog, targetSelect);
  const page = choices.find((choice) => choice.pageId === targetId)?.name ?? '';

  return createPortal(
    <dialog
      ref={dialog}
      className="dialog"
      aria-labelledby={ids.title}
      onClose={() => {
        returnFocus();
        onClosed(dialog.current?.returnValue === MOVE ? { targetId, side } : null);
      }}
    >
      <form method="dialog" className="dialog-body">
        <h2 id={ids.title} className="dialog-title">
          {t('Move selection')}
        </h2>
        <p className="dialog-text">{selectedPagesText(t, count)}</p>
        <fieldset className="field">
          <legend>{t('Place')}</legend>
          <div className="segmented">
            {SIDES.map((offeredSide) => (
              <label key={offeredSide} className="segmented-option">
                <input
                  type="radio"
                  name="side"
                  value={offeredSide}
                  checked={side === offeredSide}
                  onChange={() => setSide(offeredSide)}
                />
                <span>{offeredSide === 'after' ? t('after') : t('before')}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <div className="field">
          <label htmlFor={ids.target}>{t('the page')}</label>
          <select
            ref={targetSelect}
            id={ids.target}
            name="target"
            className="input"
            aria-describedby={ids.summary}
            value={targetId}
            onChange={(event) => setTargetId(event.target.value)}
          >
            {choices.map((choice) => (
              <option key={choice.pageId} value={choice.pageId}>
                {choice.label}
              </option>
            ))}
          </select>
        </div>
        <p id={ids.summary} className="hint">
          {moveSummaryText(t, count, side, page)}
        </p>
        <div className="dialog-actions">
          <button type="submit" value="cancel" className="btn">
            {t('Cancel')}
          </button>
          <button type="submit" value={MOVE} className="btn btn-primary">
            <Icon name="move" />
            {t('Move')}
          </button>
        </div>
      </form>
    </dialog>,
    document.body,
  );
};
