// The grading page of a quilt: its tools, each change of which the Looking Glass shows at once.
import { ConfirmButton } from '../components/ConfirmButton';
import { ErrorMessage } from '../components/ErrorMessage';
import { ToolSection } from '../components/ToolSection';
import { useDisplay } from '../hooks/useDisplay';
import { useGrade } from '../hooks/useGrade';
import { formatRoute } from '../utils/routeUtils';

/** The sections folded at first, as they are long: the colour mixer's. */
const FOLDED = /^Color Mixer/;

export function GradePage({ id }: { id: string }) {
  const grade = useGrade(id);
  const display = useDisplay();
  return (
    <main className="grade">
      <section>
        <p className="totals">
          <a className="button" href={formatRoute({ page: 'library' })}>← Library</a>
          <strong>{grade.name}</strong>
          <button disabled={!grade.changed} aria-pressed={grade.showsOriginal} onClick={grade.toggleOriginal}>
            {grade.showsOriginal ? 'Show graded' : 'Show original'}
          </button>
          <button className="primary" disabled={!grade.canSave} onClick={() => void grade.save()}>
            {grade.saving ? 'Saving…' : 'Save as new quilt'}
          </button>
          <ConfirmButton label="Reset" confirmLabel="Reset every tool" disabled={!grade.changed} onConfirm={grade.reset} />
        </p>
        {!grade.onScreen && (
          <p className="warning">
            The Looking Glass does not show this quilt.{' '}
            <button disabled={display.pending} onClick={() => void display.show(id)}>Show it</button>
          </p>
        )}
        {grade.savedName && <p className="done" role="status">Saved in the library as {grade.savedName}.</p>}
        {grade.showsOriginal && <p className="warning">The Looking Glass shows the quilt without its grade.</p>}
        <ErrorMessage text={grade.error ?? display.error} />
        {grade.loading && <p className="empty">Asking the server…</p>}
        <div className="sections">
          {grade.sections?.map(section => (
            <ToolSection key={section.title} section={section} open={!FOLDED.test(section.title)} onChange={grade.change} />
          ))}
        </div>
      </section>
    </main>
  );
}
