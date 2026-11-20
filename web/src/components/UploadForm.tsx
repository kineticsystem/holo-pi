// The upload's form: the drop area, and the layout of every file dropped, if their names do not say it. It keeps what
// is being typed itself, and reports the files dropped with the layout through onFiles.
import { useState } from 'react';
import type { UploadLayout } from '../services/HoloPiApi';
import { DropZone } from './DropZone';

/** What the drop area takes: images, and videos, also those browsers do not know, e.g. Matroska. */
const ACCEPT = 'image/*,video/*,.mkv,.mp4,.mov';

type UploadFormProps = {
  onFiles: (files: File[], layout: UploadLayout) => void;
};

/** The whole number typed, or null when the field is empty or not one. */
function count(text: string): number | null {
  const value = Number(text);
  return text.trim() !== '' && Number.isInteger(value) && value > 0 ? value : null;
}

export function UploadForm({ onFiles }: UploadFormProps) {
  const [columns, setColumns] = useState('');
  const [rows, setRows] = useState('');

  return (
    <div className="upload">
      <DropZone accept={ACCEPT}
                onFiles={files => onFiles(files, { columns: count(columns), rows: count(rows) })} />
      <fieldset>
        <legend>Layout, if the names do not give it, e.g. <code>_qs8x6a0.75</code></legend>
        <label>Columns <input type="number" min={1} value={columns} onChange={e => setColumns(e.target.value)} /></label>
        <label>Rows <input type="number" min={1} value={rows} onChange={e => setRows(e.target.value)} /></label>
      </fieldset>
    </div>
  );
}
