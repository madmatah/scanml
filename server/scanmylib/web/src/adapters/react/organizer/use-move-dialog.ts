import { type RefObject, useRef, useState } from 'react';

import type { PageId, Side } from '../../../domain/reading-order.ts';
import { useModal } from '../dialogs/use-modal.ts';
import type { MoveChoice } from './organizer-text.ts';

export interface MoveTarget {
  readonly targetId: PageId;
  readonly side: Side;
}

export interface MoveDialogState {
  readonly dialog: RefObject<HTMLDialogElement | null>;
  readonly targetSelect: RefObject<HTMLSelectElement | null>;
  readonly side: Side;
  readonly targetId: PageId;
  readonly targetName: string;
  readonly onSideChange: (side: Side) => void;
  readonly onTargetChange: (targetId: PageId) => void;
  readonly onClose: () => void;
}

export const MOVE_RETURN_VALUE = 'move';

export const useMoveDialog = (
  choices: readonly MoveChoice[],
  onClosed: (target: MoveTarget | null) => void,
): MoveDialogState => {
  const dialog = useRef<HTMLDialogElement>(null);
  const targetSelect = useRef<HTMLSelectElement>(null);
  const [side, setSide] = useState<Side>('before');
  const [targetId, setTargetId] = useState<PageId>(choices[0]?.pageId ?? '');
  const returnFocus = useModal(dialog, targetSelect);

  return {
    dialog,
    targetSelect,
    side,
    targetId,
    targetName: choices.find((choice) => choice.pageId === targetId)?.name ?? '',
    onSideChange: setSide,
    onTargetChange: setTargetId,
    onClose: () => {
      returnFocus();
      onClosed(dialog.current?.returnValue === MOVE_RETURN_VALUE ? { targetId, side } : null);
    },
  };
};
