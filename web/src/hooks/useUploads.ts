// The uploads' view model: a queue of files, sent to the library one after another, each with its progress, which
// cancel() stops; a file that fails does not stop the next. Each file in is put in the list, and the first of those
// dropped together is shown at once. Used by the upload panel.
import { useEffect, useRef, useState } from 'react';
import { useHoloPiStore } from '../model/HoloPiStoreContext';
import type { Medium, UploadLayout, UploadOptions } from '../services/HoloPiApi';
import { useServices } from '../services/ServicesContext';

export type UploadStatus = 'waiting' | 'sending' | 'done' | 'failed' | 'stopped';

export type UploadJob = {
  id: number;
  file: File;
  options: UploadOptions;
  status: UploadStatus;
  progress: number; // 0 to 100
  error: string | null;
  medium: Medium | null;
};

export function useUploads() {
  const { dispatch } = useHoloPiStore();
  const { api } = useServices();
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const waitingRef = useRef<UploadJob[]>([]); // The files still to send, in order.
  const currentRef = useRef<{ id: number; controller: AbortController } | null>(null);
  const nextIdRef = useRef(1);
  const mountedRef = useRef(true);

  // Stop the upload running, and forget the others, when the panel goes.
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      waitingRef.current = [];
      currentRef.current?.controller.abort();
    };
  }, []);

  function update(id: number, fields: Partial<UploadJob>) {
    setJobs(all => all.map(job => (job.id === id ? { ...job, ...fields } : job)));
  }

  async function sendNext() {
    if (currentRef.current) return; // One at a time: the network is shared.
    const job = waitingRef.current.shift();
    if (!job) return;
    const controller = new AbortController();
    currentRef.current = { id: job.id, controller };
    update(job.id, { status: 'sending', progress: 0 });
    const result = await api.upload(job.file, job.options, sent => update(job.id, { progress: Math.round(sent * 100) }),
                                    controller.signal);
    currentRef.current = null;
    if (!mountedRef.current) return;
    if (result.ok) {
      update(job.id, { status: 'done', progress: 100, medium: result.value });
      dispatch({ type: 'mediumUploaded', medium: result.value });
      if (job.options.play) {
        const display = await api.getDisplay();
        if (display.ok) dispatch({ type: 'displayRead', display: display.value });
      }
    } else {
      update(job.id, result.error === 'stopped' ? { status: 'stopped' } : { status: 'failed', error: result.error });
    }
    void sendNext();
  }

  /**
   * Queues files with the same layout. The first is shown as soon as it is in, a single file as well as the first of
   * several: what we upload, we want to see, and showing each of several in turn would end on the last.
   */
  function add(files: File[], layout: UploadLayout) {
    if ((layout.columns === null) !== (layout.rows === null)) {
      setError('Give both columns and rows, or neither.');
      return;
    }
    setError(null);
    const added = files.map((file, index): UploadJob => ({
      id: nextIdRef.current++, file, options: { ...layout, reverse: false, play: index === 0 },
      status: 'waiting', progress: 0, error: null, medium: null,
    }));
    waitingRef.current.push(...added);
    setJobs(all => [...all, ...added]);
    void sendNext();
  }

  function cancel(id: number) {
    if (currentRef.current?.id === id) {
      currentRef.current.controller.abort();
      return;
    }
    waitingRef.current = waitingRef.current.filter(job => job.id !== id);
    update(id, { status: 'stopped' });
  }

  function cancelAll() {
    for (const job of waitingRef.current) update(job.id, { status: 'stopped' });
    waitingRef.current = [];
    currentRef.current?.controller.abort();
  }

  function clearFinished() {
    setJobs(all => all.filter(job => job.status === 'waiting' || job.status === 'sending'));
  }

  const busy = jobs.some(job => job.status === 'waiting' || job.status === 'sending');
  return { jobs, busy, error, add, cancel, cancelAll, clearFinished };
}
