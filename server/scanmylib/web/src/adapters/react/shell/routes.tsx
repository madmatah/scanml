import type { RouteObject } from 'react-router';

import { Library } from '../library/library.tsx';
import { Login } from '../login/login.tsx';
import { Pairing } from '../pairing/pairing.tsx';
import type { RouteName } from './navigation.ts';
import { Shell, type ShellServices } from './shell.tsx';

export function createRoutes(services: ShellServices): RouteObject[] {
  return [
    {
      element: <Shell services={services} />,
      children: [
        {
          id: 'home' satisfies RouteName,
          index: true,
          element: (
            <Library
              catalog={services.catalog}
              engineStatus={services.engineStatus}
              toasts={services.toasts}
              uuids={services.uuids}
              dates={services.dates}
            />
          ),
        },
        {
          id: 'pairing' satisfies RouteName,
          path: 'pairing',
          element: <Pairing source={services.pairing} clipboard={services.clipboard} toasts={services.toasts} />,
        },
        { id: 'login' satisfies RouteName, path: 'login', element: <Login session={services.session} /> },
        { id: 'unknown' satisfies RouteName, path: '*', element: null },
      ],
    },
  ];
}
