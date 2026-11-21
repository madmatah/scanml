import type { RouteObject } from 'react-router';

import { DocumentScreen } from '../document/document-screen.tsx';
import { LibraryScreen } from '../library/library-screen.tsx';
import { LoginScreen } from '../login/login-screen.tsx';
import { PageScreen } from '../page/page-screen.tsx';
import { PairingScreen } from '../pairing/pairing-screen.tsx';
import { ReaderScreen } from '../reader/reader-screen.tsx';
import type { RouteName } from './navigation.ts';
import { Shell, type ShellServices } from './shell.tsx';

export const createRoutes = (services: ShellServices): RouteObject[] => {
  return [
    {
      element: <Shell services={services} />,
      children: [
        {
          id: 'home' satisfies RouteName,
          index: true,
          element: (
            <LibraryScreen
              catalog={services.catalog}
              libraryView={services.libraryView}
              engineStatus={services.engineStatus}
              toasts={services.toasts}
              uuids={services.uuids}
              dates={services.dates}
              formatting={services.formatting}
            />
          ),
        },
        {
          id: 'document' satisfies RouteName,
          path: 'documents/:documentId',
          element: (
            <DocumentScreen
              store={services.documents}
              engineStatus={services.engineStatus}
              scheduler={services.scheduler}
              toasts={services.toasts}
              clipboard={services.clipboard}
              formatting={services.formatting}
              uploads={services.uploads}
              uuids={services.uuids}
            />
          ),
        },
        {
          id: 'reader' satisfies RouteName,
          path: 'documents/:documentId/read',
          element: (
            <ReaderScreen
              documents={services.documents}
              toasts={services.toasts}
              typesetFormulas={services.typesetFormulas}
            />
          ),
        },
        {
          id: 'page' satisfies RouteName,
          path: 'pages/:pageId',
          element: (
            <PageScreen
              pages={services.pages}
              documents={services.documents}
              scheduler={services.scheduler}
              toasts={services.toasts}
              clipboard={services.clipboard}
              formatting={services.formatting}
              dates={services.dates}
              typesetFormulas={services.typesetFormulas}
            />
          ),
        },
        {
          id: 'pairing' satisfies RouteName,
          path: 'pairing',
          element: <PairingScreen source={services.pairing} clipboard={services.clipboard} toasts={services.toasts} />,
        },
        { id: 'login' satisfies RouteName, path: 'login', element: <LoginScreen session={services.session} /> },
        { id: 'unknown' satisfies RouteName, path: '*', element: null },
      ],
    },
  ];
};
