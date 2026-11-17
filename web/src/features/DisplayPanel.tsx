// What the Looking Glass shows, and the buttons to show the test pattern or black.
import { DisplayCard } from '../components/DisplayCard';
import { ErrorMessage } from '../components/ErrorMessage';
import { useDisplay } from '../hooks/useDisplay';

export function DisplayPanel() {
  const { display, error, pending, showTestPattern, showBlack } = useDisplay();
  return (
    <section>
      <h2>On the Looking Glass</h2>
      <DisplayCard display={display} />
      <div className="buttons">
        <button disabled={pending} onClick={() => void showTestPattern()}>Test pattern</button>
        <button disabled={pending || display?.source === null} onClick={() => void showBlack()}>Black</button>
      </div>
      <ErrorMessage text={error} />
    </section>
  );
}
