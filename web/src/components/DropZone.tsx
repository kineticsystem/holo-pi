// An area to drop files on, or to click, or to press Enter on, to choose them: reports them all through onFiles.
import { useRef, useState, type DragEvent, type KeyboardEvent } from 'react';

type DropZoneProps = { accept: string; disabled?: boolean; onFiles: (files: File[]) => void };

export function DropZone({ accept, disabled = false, onFiles }: DropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  function handleDrop(event: DragEvent) {
    event.preventDefault();
    setOver(false);
    if (!disabled && event.dataTransfer.files.length > 0) onFiles(Array.from(event.dataTransfer.files));
  }

  function handleKey(event: KeyboardEvent) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      inputRef.current?.click();
    }
  }

  return (
    <div className={`dropzone${over ? ' over' : ''}${disabled ? ' disabled' : ''}`} role="button" tabIndex={0}
         aria-label="Drop files here, or choose them" aria-disabled={disabled}
         onClick={() => !disabled && inputRef.current?.click()} onKeyDown={handleKey}
         onDragOver={event => { event.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
         onDrop={handleDrop}>
      <strong>Drop quilts and videos here</strong>
      <span>or click to choose them, one or many</span>
      <input ref={inputRef} type="file" multiple accept={accept} hidden disabled={disabled}
             data-testid="dropzone-input"
             onChange={event => {
               const files = Array.from(event.target.files ?? []);
               event.target.value = ''; // The same files may be chosen again.
               if (files.length > 0) onFiles(files);
             }} />
    </div>
  );
}
