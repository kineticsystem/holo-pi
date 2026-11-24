// What the Looking Glass shows, in words: what, whether it is on the screen, and how a video plays.
import type { Display } from '../services/HoloPiApi';

export function DisplayCard({ display }: { display: Display | null }) {
  if (display === null) return <p className="empty">Asking the server…</p>;
  if (display.source === null) return <p className="black">Black: nothing is shown.</p>;
  const what = display.source === 'test pattern' ? 'The test pattern'
    : display.source === 'default' ? `The default quilt, ${display.name}` : display.name;
  return (
    <dl className="display">
      <dt>Showing</dt>
      <dd>{what}{display.reverse ? ', views in reverse' : ''}</dd>
      <dt>Kind</dt>
      <dd>{display.kind}</dd>
      {display.media?.grade && (
        <>
          <dt>Grade</dt>
          <dd>{display.media.grade === 'on' ? 'on' : 'off: shown without it'}</dd>
        </>
      )}
      <dt>On the screen</dt>
      <dd>{display.shown ? `yes, on ${display.shown_on}` : `not yet: ${display.error ?? 'starting'}`}</dd>
      {display.frame_rate !== null && (
        <>
          <dt>Frame rate</dt>
          <dd>{display.frame_rate} fps{display.media?.fps ? ` of ${Math.round(display.media.fps)}` : ''}</dd>
        </>
      )}
      {display.decoder && (
        <>
          <dt>Decoder</dt>
          <dd>{display.decoder}</dd>
        </>
      )}
      {display.warning && (
        <>
          <dt>Warning</dt>
          <dd className="warning">{display.warning}</dd>
        </>
      )}
    </dl>
  );
}
