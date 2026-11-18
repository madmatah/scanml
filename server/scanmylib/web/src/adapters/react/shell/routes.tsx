import type { RouteObject } from 'react-router';

import { Login } from '../login/login.tsx';
import { Home } from './home.tsx';
import type { RouteName } from './navigation.ts';
import { Shell, type ShellServices } from './shell.tsx';

export function createRoutes(services: ShellServices): RouteObject[] {
  return [
    {
      element: <Shell services={services} />,
      children: [
        { id: 'home' satisfies RouteName, index: true, element: <Home /> },
        { id: 'login' satisfies RouteName, path: 'login', element: <Login session={services.session} /> },
        { id: 'unknown' satisfies RouteName, path: '*', element: null },
      ],
    },
  ];
}
