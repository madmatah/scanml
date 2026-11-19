import type { FC, MouseEvent, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router';

import type { EngineStatus } from '../../../application/engine-status.ts';
import type { NumberFormatting } from '../../../domain/formatting.ts';
import { EngineStatusBadge } from '../engine-status/engine-status-badge.tsx';
import { BrandMark } from './brand-mark.tsx';
import { Icon } from './icon.tsx';
import { BRAND_NAME, PATHS, type Section } from './navigation.ts';

const BRAND_MARK_PIXELS = 28;

export interface HeaderProps {
  readonly isSignedIn: boolean;
  readonly section: Section | null;
  readonly engineStatus: EngineStatus;
  readonly formatting: NumberFormatting;
  readonly onSignOut: () => void;
}

interface HeaderLinkProps {
  readonly to: string;
  readonly className?: string;
  readonly isCurrent?: boolean;
  readonly children: ReactNode;
}

const HeaderLink: FC<HeaderLinkProps> = ({ to, className, isCurrent = false, children }) => {
  const location = useLocation();
  // A link to the address already shown changes nothing, as a link to the same fragment does: the router would
  // otherwise enter it again, and the shell move the focus and the scroll as for a new screen.
  const stayOnSameAddress = (event: MouseEvent<HTMLAnchorElement>): void => {
    if (location.pathname === to) event.preventDefault();
  };
  return (
    <Link to={to} className={className} aria-current={isCurrent ? 'page' : undefined} onClick={stayOnSameAddress}>
      {children}
    </Link>
  );
};

export const Header: FC<HeaderProps> = ({ isSignedIn, section, engineStatus, formatting, onSignOut }) => {
  const { t } = useTranslation();
  return (
    <header className="app-header" id="app-header" hidden={!isSignedIn}>
      <HeaderLink to={PATHS.home} className="brand">
        <BrandMark sizePixels={BRAND_MARK_PIXELS} />
        <span>{BRAND_NAME}</span>
      </HeaderLink>
      <nav className="app-nav" aria-label={t('Main navigation')}>
        <HeaderLink to={PATHS.home} isCurrent={section === 'library'}>
          {t('Library')}
        </HeaderLink>
        <HeaderLink to={PATHS.pairing} isCurrent={section === 'pairing'}>
          {t('Pairing')}
        </HeaderLink>
      </nav>
      <div className="header-tools">
        <EngineStatusBadge engineStatus={engineStatus} formatting={formatting} />
        <button type="button" className="btn btn-ghost btn-compact" id="logout-button" onClick={onSignOut}>
          <Icon name="sign-out" />
          <span className="btn-label">{t('Sign out', { context: 'header' })}</span>
        </button>
      </div>
    </header>
  );
};
