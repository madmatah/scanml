export interface Photo {
  readonly type: string;
  readonly size: number;
}

export type PhotoRejection =
  | { readonly kind: 'unsupported-format' }
  | { readonly kind: 'too-large' }
  | { readonly kind: 'empty' };

export const ACCEPTED_TYPES: readonly string[] = ['image/jpeg', 'image/png', 'image/webp'];
export const MAX_UPLOAD_BYTES = 40 * 1024 * 1024;

export function checkPhoto(photo: Photo): PhotoRejection | null {
  if (photo.type !== '' && !ACCEPTED_TYPES.includes(photo.type)) return { kind: 'unsupported-format' };
  if (photo.size > MAX_UPLOAD_BYTES) return { kind: 'too-large' };
  if (photo.size === 0) return { kind: 'empty' };
  return null;
}
