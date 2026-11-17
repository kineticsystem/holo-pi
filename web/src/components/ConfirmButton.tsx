// A button that asks for a second click before it acts, for what cannot be undone, e.g. removing a medium.
import { useState } from 'react';

type ConfirmButtonProps = { label: string; confirmLabel: string; disabled?: boolean; onConfirm: () => void };

export function ConfirmButton({ label, confirmLabel, disabled = false, onConfirm }: ConfirmButtonProps) {
  const [armed, setArmed] = useState(false);
  if (!armed) {
    return <button className="danger" disabled={disabled} onClick={() => setArmed(true)}>{label}</button>;
  }
  return (
    <span className="confirm">
      <button className="danger" disabled={disabled} onClick={() => { setArmed(false); onConfirm(); }}>
        {confirmLabel}
      </button>
      <button onClick={() => setArmed(false)}>Cancel</button>
    </span>
  );
}
