import type { RouteObject } from 'react-router';

import type { Session } from '../../../application/session.ts';
import { Login } from '../login/login.tsx';
import { Home } from './home.tsx';
import type { RouteName } from './navigation.ts';
import { Shell } from './shell.tsx';

export function createRoutes(session: Session): RouteObject[] {
  return [
    {
      element: <Shell session={session} />,
      children: [
        { id: 'home' satisfies RouteName, index: true, element: <Home /> },
        { id: 'login' satisfies RouteName, path: 'login', element: <Login session={session} /> },
        { id: 'unknown' satisfies RouteName, path: '*', element: null },
      ],
    },
  ];
}
