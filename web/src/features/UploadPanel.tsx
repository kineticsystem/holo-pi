// Uploads quilts and videos to the library, one or many, dropped or chosen; the first is shown at once.
import { ErrorMessage } from '../components/ErrorMessage';
import { UploadForm } from '../components/UploadForm';
import { UploadQueue } from '../components/UploadQueue';
import { useUploads } from '../hooks/useUploads';

export function UploadPanel() {
  const { jobs, error, add, cancel, cancelAll, clearFinished } = useUploads();
  return (
    <section>
      <h2>Upload</h2>
      <UploadForm onFiles={add} />
      <ErrorMessage text={error} />
      <UploadQueue jobs={jobs} onCancel={cancel} onCancelAll={cancelAll} onClear={clearFinished} />
    </section>
  );
}
