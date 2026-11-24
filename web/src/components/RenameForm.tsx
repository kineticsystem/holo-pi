// A medium's name, to change in place: Enter or Save takes it, Escape or Cancel leaves it as it was. It stays, with what was
// typed, until the new name is taken, so that a refused one can be corrected.
import { useState, type FormEvent, type KeyboardEvent } from 'react';
import { splitName } from '../utils/nameUtils';

type RenameFormProps = {
  name: string;
  /** Whether the new name was taken. */
  onRename: (name: string) => Promise<boolean>;
  /** It is over: renamed, or left as it was. */
  onDone: () => void;
};

export function RenameForm({ name, onRename, onDone }: RenameFormProps) {
  const [typed, setTyped] = useState(name);
  const [busy, setBusy] = useState(false);
  const wanted = typed.trim();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy || !wanted) return;
    if (wanted === name) {
      onDone();
      return;
    }
    setBusy(true);
    const renamed = await onRename(wanted);
    setBusy(false);
    if (renamed) onDone();
  }

  function handleKeyDown(event: KeyboardEvent) {
    event.stopPropagation(); // The table's arrows show the media above and below: here, they move in the text.
    if (event.key === 'Escape') onDone();
  }

  return (
    <form className="rename" onSubmit={event => void handleSubmit(event)} onKeyDown={handleKeyDown}>
      <input aria-label={`New name of ${name}`} value={typed} autoFocus readOnly={busy} size={Math.max(20, typed.length)}
             onFocus={event => event.target.setSelectionRange(0, splitName(name).title.length)}
             onChange={event => setTyped(event.target.value)} />
      <button className="primary" type="submit" disabled={busy || !wanted}>Save</button>
      <button type="button" onClick={onDone}>Cancel</button>
    </form>
  );
}
