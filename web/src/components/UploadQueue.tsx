// The files being uploaded and those done: their state, the progress of the one being sent, the warning of each
// video not in H.265, with a count of them at the top so that none hides in a long list, and buttons to stop them
// and to clear the list.
import type { UploadJob } from '../hooks/useUploads';
import { formatBytes } from '../utils/formatUtils';

type UploadQueueProps = {
  jobs: UploadJob[];
  onCancel: (id: number) => void;
  onCancelAll: () => void;
  onClear: () => void;
};

function statusOf(job: UploadJob): string {
  switch (job.status) {
    case 'waiting':
      return 'waiting';
    case 'sending':
      return `sending ${job.progress}%`;
    case 'done':
      return job.medium?.warning ? 'kept, with a warning' : 'kept';
    case 'failed':
      return 'failed';
    case 'stopped':
      return 'stopped';
  }
}

export function UploadQueue({ jobs, onCancel, onCancelAll, onClear }: UploadQueueProps) {
  if (jobs.length === 0) return null;
  const running = jobs.some(job => job.status === 'waiting' || job.status === 'sending');
  const finished = jobs.some(job => job.status !== 'waiting' && job.status !== 'sending');
  const warned = jobs.filter(job => job.medium?.warning).length;
  return (
    <div className="queue">
      {warned > 0 && (
        <p className="warning" role="status">
          {warned === 1 ? 'One of the files is' : `${warned} of the files are`} not in H.265 (HEVC): a Raspberry Pi 5
          decodes {warned === 1 ? 'it' : 'them'} on its processor, maybe too slowly. See the warning of each below.
        </p>
      )}
      <ul>
        {jobs.map(job => (
          <li key={job.id} className={job.medium?.warning ? `${job.status} warned` : job.status}>
            <div className="line">
              <span className="name">{job.file.name}</span>
              <span className="size">{formatBytes(job.file.size)}</span>
              <span className="status">{statusOf(job)}</span>
              {(job.status === 'waiting' || job.status === 'sending') && (
                <button aria-label={`Stop ${job.file.name}`} onClick={() => onCancel(job.id)}>Stop</button>
              )}
            </div>
            {job.status === 'sending' && <progress max={100} value={job.progress} aria-label={`Sending ${job.file.name}`} />}
            {job.error && <div className="error">{job.error}</div>}
            {job.medium?.warning && <div className="warning">{job.medium.warning}</div>}
          </li>
        ))}
      </ul>
      <div className="buttons">
        {running && <button onClick={onCancelAll}>Stop all</button>}
        {finished && <button onClick={onClear}>Clear the finished</button>}
      </div>
    </div>
  );
}
