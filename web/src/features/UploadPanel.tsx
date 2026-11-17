// Uploads quilts and videos to the library, one or many, dropped or chosen, and shows the first at once if asked.
import { ErrorMessage } from '../components/ErrorMessage';
import { UploadForm } from '../components/UploadForm';
import { UploadQueue } from '../components/UploadQueue';
import { usePersistentState } from '../hooks/usePersistentState';
import { useUploads } from '../hooks/useUploads';
import { StorageKeys } from '../utils/storageKeys';

export function UploadPanel() {
  const { jobs, error, add, cancel, cancelAll, clearFinished } = useUploads();
  const [play, setPlay] = usePersistentState(StorageKeys.upload.PLAY_AFTER_UPLOAD, true);
  return (
    <section>
      <h2>Upload</h2>
      <UploadForm play={play} onPlayChange={setPlay} onFiles={add} />
      <ErrorMessage text={error} />
      <UploadQueue jobs={jobs} onCancel={cancel} onCancelAll={cancelAll} onClear={clearFinished} />
    </section>
  );
}
