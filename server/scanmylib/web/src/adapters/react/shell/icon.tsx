// Line icons, 24 pixels square, stroked in the color of their text (.icon in app.css). They are decorative: the text
// beside them, or the label of their control, carries the meaning.
const ICON_PATHS = {
  alert: 'M12 3.5 21.5 20h-19zM12 10v4.5M12 17.25h.01',
  book: 'M3.5 5.5c2.9-1.2 5.8-1.2 8.5.6 2.7-1.8 5.6-1.8 8.5-.6v13.4c-2.9-1.1-5.8-1.1-8.5.6-2.7-1.7-5.6-1.7-8.5-.6zM12 6.1v13.4',
  eye: 'M2.5 12S6 5 12 5s9.5 7 9.5 7-3.5 7-9.5 7-9.5-7-9.5-7zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  'eye-off': 'M2.5 12S6 5 12 5s9.5 7 9.5 7-3.5 7-9.5 7-9.5-7-9.5-7zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM4 4l16 16',
  phone: 'M7.5 2.5h9a1 1 0 0 1 1 1v17a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1v-17a1 1 0 0 1 1-1zM11 18h2',
  plus: 'M12 5v14M5 12h14',
  refresh: 'M20 11a8 8 0 0 0-14.9-3.9M4 4v4h4M4 13a8 8 0 0 0 14.9 3.9M20 20v-4h-4',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4',
  'sign-out': 'M9 20H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h3M16 17l5-5-5-5M21 12H9',
  x: 'M6 6l12 12M18 6 6 18',
} as const;

export type IconName = keyof typeof ICON_PATHS;

export function Icon({ name }: { readonly name: IconName }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d={ICON_PATHS[name]} />
    </svg>
  );
}
