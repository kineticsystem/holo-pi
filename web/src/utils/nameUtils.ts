// The parts of a medium's name. Used by RenameForm, to select the one we mostly want to change.

/** A name's title, and what follows it: its layout and its extension, e.g. helix and _qs8x6a0.75.mp4. */
export function splitName(name: string): { title: string; rest: string } {
  const match = /_qs\d+x\d+.*$|\.[a-z][a-z0-9]*$/i.exec(name);
  const at = match && match.index > 0 ? match.index : name.length;
  return { title: name.slice(0, at), rest: name.slice(at) };
}
