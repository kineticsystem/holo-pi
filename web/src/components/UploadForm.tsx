// The upload's options, for every file dropped: their layout if their names do not say, the order of their views,
// and whether to show the first at once. It keeps what is being typed itself, and reports the files dropped with
// the options through onFiles.
import { useState } from 'react';
import type { UploadOptions } from '../services/HoloPiApi';
import { DropZone } from './DropZone';

/** What the drop area takes: images, and videos, also those browsers do not know, e.g. Matroska. */
const ACCEPT = 'image/*,video/*,.mkv,.mp4,.mov';

type UploadFormProps = {
  play: boolean;
  onPlayChange: (play: boolean) => void;
  onFiles: (files: File[], options: UploadOptions) => void;
};

/** The whole number typed, or null when the field is empty or not one. */
function count(text: string): number | null {
  const value = Number(text);
  return text.trim() !== '' && Number.isInteger(value) && value > 0 ? value : null;
}

export function UploadForm({ play, onPlayChange, onFiles }: UploadFormProps) {
  const [columns, setColumns] = useState('');
  const [rows, setRows] = useState('');
  const [reverse, setReverse] = useState(false);

  return (
    <div className="upload">
      <DropZone accept={ACCEPT}
                onFiles={files => onFiles(files, { columns: count(columns), rows: count(rows), reverse, play })} />
      <fieldset>
        <legend>Layout, if the names do not give it, e.g. <code>_qs8x6a0.75</code></legend>
        <label>Columns <input type="number" min={1} value={columns} onChange={e => setColumns(e.target.value)} /></label>
        <label>Rows <input type="number" min={1} value={rows} onChange={e => setRows(e.target.value)} /></label>
        <label className="check">
          <input type="checkbox" checked={reverse} onChange={e => setReverse(e.target.checked)} /> Views in reverse
        </label>
      </fieldset>
      <label className="check">
        <input type="checkbox" checked={play} onChange={e => onPlayChange(e.target.checked)} />
        Show it at once (the first, of several)
      </label>
    </div>
  );
}
