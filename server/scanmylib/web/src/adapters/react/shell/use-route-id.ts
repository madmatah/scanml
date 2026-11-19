import { useParams } from 'react-router';

import { idOfAddress } from './navigation.ts';

export type RouteIdParameter = 'documentId' | 'pageId';

export const useRouteId = (parameter: RouteIdParameter): string | null => {
  return idOfAddress(useParams()[parameter]);
};
