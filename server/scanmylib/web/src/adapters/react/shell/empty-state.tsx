import type { ReactNode } from 'react';

import { Icon, type IconName } from './icon.tsx';

export interface EmptyStateProps {
  readonly iconName?: IconName;
  readonly title: string;
  readonly message?: string;
  readonly actions?: ReactNode;
}

export const EmptyState = ({ iconName, title, message, actions }: EmptyStateProps) => {
  return (
    <div className="state state-empty">
      {iconName !== undefined && (
        <span className="state-icon">
          <Icon name={iconName} />
        </span>
      )}
      <h2 className="state-title">{title}</h2>
      {message !== undefined && message !== '' && <p className="state-text">{message}</p>}
      {actions !== undefined && <div className="state-actions">{actions}</div>}
    </div>
  );
};
