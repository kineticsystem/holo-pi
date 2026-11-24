// The list of the quilts to copy a grade from, by their names. It shows the one copied, or else what it is for.
import type { Medium } from '../services/HoloPiApi';

type GradeSourceSelectProps = {
  sources: Medium[];
  /** The source whose grade is the one there is now, or null. */
  copiedId: string | null;
  disabled: boolean;
  onCopy: (id: string) => void;
};

export function GradeSourceSelect({ sources, copiedId, disabled, onCopy }: GradeSourceSelectProps) {
  const value = sources.some(source => source.id === copiedId) ? copiedId! : '';
  return (
    <select aria-label="Copy grade from" value={value} disabled={disabled || sources.length === 0}
            title={sources.length === 0 ? 'No other quilt is graded' : "Replace this quilt's grade with another quilt's"}
            onChange={event => onCopy(event.target.value)}>
      <option value="" disabled>Copy grade from…</option>
      {sources.map(source => <option key={source.id} value={source.id}>{source.name}</option>)}
    </select>
  );
}
