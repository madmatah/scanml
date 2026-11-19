import type { FC } from 'react';
import { useTranslation } from 'react-i18next';

import type { EngineStatusState } from '../../../application/engine-status.ts';
import type { NumberFormatting } from '../../../domain/formatting.ts';
import { engineDetails, engineStateOf, pendingPagesText } from './engine-status-text.ts';
import { usePanelDismissal } from './use-panel-dismissal.ts';

const PANEL_ID = 'engine-panel';

export interface EngineStatusBadgeProps {
  readonly engine: EngineStatusState;
  readonly formatting: NumberFormatting;
  readonly isOpen: boolean;
  readonly onToggle: () => void;
  readonly onClose: () => void;
}

export const EngineStatusBadge: FC<EngineStatusBadgeProps> = ({ engine, formatting, isOpen, onToggle, onClose }) => {
  const { t } = useTranslation();
  const { container, badge } = usePanelDismissal(isOpen, onClose);
  const engineState = engineStateOf(t, engine);
  const pendingPages = pendingPagesText(t, formatting, engine);
  const details = engineDetails(t, formatting, engine, engineState.label);

  return (
    <div className="engine-status" id="engine-status" ref={container}>
      <button
        type="button"
        className="engine-badge"
        aria-expanded={isOpen}
        aria-controls={PANEL_ID}
        data-tone={engineState.tone}
        ref={badge}
        onClick={onToggle}
      >
        <span className="status-dot" aria-hidden="true" />
        <span className="engine-label">{engineState.label}</span>
        <span className="engine-queue" hidden={pendingPages === null}>
          {pendingPages ?? ''}
        </span>
      </button>
      <div id={PANEL_ID} className="engine-panel" hidden={!isOpen}>
        {engineState.description !== '' && <p className="engine-panel-text">{engineState.description}</p>}
        <dl className="details-list">
          {details.map(({ term, description, isPath }) => (
            <div key={term}>
              <dt>{term}</dt>
              <dd>{isPath ? <code className="path">{description}</code> : description}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
};
