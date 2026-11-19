export const decodeErrorDetail = (body: unknown): string => {
  if (typeof body !== 'object' || body === null || !('detail' in body)) return '';
  const { detail } = body;
  if (typeof detail === 'string') return detail;
  if (!Array.isArray(detail)) return '';
  return detail
    .map((error: unknown) =>
      typeof error === 'object' && error !== null && 'msg' in error && typeof error.msg === 'string' ? error.msg : '',
    )
    .filter((message) => message !== '')
    .join('; ');
};
