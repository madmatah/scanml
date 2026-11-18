import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { useTranslation } from 'react-i18next';

import type { EngineStatus } from '../../../application/engine-status.ts';
import type { NumberFormatting } from '../../../domain/formatting.ts';
import { engineDetails, engineStateOf, pendingPagesText } from './engine-status-text.ts';

const PANEL_ID = 'engine-panel';

export interface EngineStatusBadgeProps {
  readonly engineStatus: EngineStatus;
  readonly formatting: NumberFormatting;
}

export function EngineStatusBadge({ engineStatus, formatting }: EngineStatusBadgeProps) {
  const { t } = useTranslation();
  const state = useSyncExternalStore(engineStatus.subscribe, engineStatus.getSnapshot);
  const [isOpen, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const badge = useRef<HTMLButtonElement>(null);
  const engineState = engineStateOf(t, state);
  const pendingPages = pendingPagesText(t, formatting, state);
  const details = engineDetails(t, formatting, state, engineState.label);

  useEffect(() => {
    if (!isOpen) return;
    function closeOnClickOutside(event: MouseEvent): void {
      if (event.target instanceof Node && container.current?.contains(event.target)) return;
      setOpen(false);
    }
    function closeOnEscape(event: KeyboardEvent): void {
      if (event.key !== 'Escape') return;
      setOpen(false);
      badge.current?.focus();
    }
    document.addEventListener('click', closeOnClickOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('click', closeOnClickOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [isOpen]);

  return (
    <div className="engine-status" id="engine-status" ref={container}>
      <button
        type="button"
        className="engine-badge"
        aria-expanded={isOpen}
        aria-controls={PANEL_ID}
        data-tone={engineState.tone}
        ref={badge}
        onClick={() => setOpen(!isOpen)}
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
}
