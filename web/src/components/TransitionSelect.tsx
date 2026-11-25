// How one medium of the playlist goes into the next, and how long that takes, unless it goes at once.
import type { Transition } from '../services/HoloPiApi';
import { TRANSITION_RANGE, TRANSITIONS } from '../utils/playlistUtils';
import { NumberField } from './NumberField';

type TransitionSelectProps = {
  transition: Transition;
  seconds: number;
  disabled: boolean;
  /** Why there are no transitions, if so. */
  why: string | null;
  onTransition: (transition: Transition) => void;
  onSeconds: (seconds: number) => void;
};

export function TransitionSelect({ transition, seconds, disabled, why, onTransition, onSeconds }: TransitionSelectProps) {
  return (
    <>
      <label title={why ?? 'How one goes into the next'}>
        Transition{' '}
        <select value={why ? 'cut' : transition} disabled={disabled || why !== null}
                onChange={event => onTransition(event.target.value as Transition)}>
          {TRANSITIONS.map(({ kind, label }) => <option key={kind} value={kind}>{label}</option>)}
        </select>
      </label>
      {!why && transition !== 'cut' && (
        <NumberField label="Seconds of the transition" unit="seconds" value={seconds} {...TRANSITION_RANGE}
                     disabled={disabled} onChange={onSeconds} />
      )}
    </>
  );
}
