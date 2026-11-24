// What the Looking Glass shows, and the buttons to show the test pattern or black, or to grade the quilt shown.
import { DisplayCard } from '../components/DisplayCard';
import { ErrorMessage } from '../components/ErrorMessage';
import { useDisplay } from '../hooks/useDisplay';
import { formatRoute } from '../utils/routeUtils';

export function DisplayPanel() {
  const { display, gradable, error, pending, showTestPattern, showBlack } = useDisplay();
  return (
    <section>
      <h2>On the Looking Glass</h2>
      <DisplayCard display={display} />
      <div className="buttons">
        <button disabled={pending} onClick={() => void showTestPattern()}>Test pattern</button>
        <button disabled={pending || display?.source === null} onClick={() => void showBlack()}>Black</button>
        <button disabled={gradable.id === null} title={gradable.why ?? 'Change the light and the colours of this quilt'}
                onClick={() => { if (gradable.id) window.location.hash = formatRoute({ page: 'grade', id: gradable.id }); }}>
          Grade…
        </button>
      </div>
      <ErrorMessage text={error} />
    </section>
  );
}
