// Small icon set ported from poc-planner/index.html's `ICONS` map (same path data, same 24x24
// viewBox) -- only the names Home.tsx actually needs, not the planner's full set.
const ICONS: Record<string, string> = {
  home: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',
  layout: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
  book: '<path d="M4 4.5A2.5 2.5 0 016.5 2H20v16H6.5A2.5 2.5 0 004 20.5v-16z"/><path d="M4 20.5A2.5 2.5 0 006.5 18H20"/>',
  folder: '<path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"/>',
  chevronR: '<path d="M9 6l6 6-6 6"/>',
  broadcast:
    '<circle cx="12" cy="12" r="2"/><path d="M8.5 8.5a5 5 0 000 7M15.5 8.5a5 5 0 010 7M5 5a9 9 0 000 14M19 5a9 9 0 010 14"/>',
};

export type IconName = keyof typeof ICONS;

export function Icon({ name, className }: { name: IconName; className?: string }) {
  return (
    <svg
      className={"icon" + (className ? " " + className : "")}
      viewBox="0 0 24 24"
      dangerouslySetInnerHTML={{ __html: ICONS[name] }}
    />
  );
}
