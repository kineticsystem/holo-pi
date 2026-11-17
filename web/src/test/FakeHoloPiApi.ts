// A HoloPi API in memory, for the tests: a library, a display, and failures on request.
import type { Display, HoloPiApi, MediaList, Medium, ServerStatus, UploadOptions } from '../services/HoloPiApi';
import { err, ok, type Result } from '../utils/result';

export function medium(fields: Partial<Medium> = {}): Medium {
  return {
    id: 'a1', name: 'helix_qs8x6a0.75.mp4', kind: 'quilt video', size: 1000, uploaded: '2026-11-17T11:45:02+00:00',
    width: 3360, height: 3360, columns: 8, rows: 6, reverse: false, fps: 24, frames: 480, duration: 20,
    codec: 'hevc', warning: null, shown: false, ...fields,
  };
}

const BLACK: Display = {
  source: null, media: null, name: null, kind: null, reverse: false, shown: false, shown_on: null, error: null,
  frame_rate: null, decoder: null, warning: null, then: null,
};

export class FakeHoloPiApi implements HoloPiApi {
  media: Medium[];
  display: Display = BLACK;
  failWith: string | null = null; // Every request fails with this, when set.
  uploads: { file: File; options: UploadOptions }[] = [];
  /** Uploads wait for finishUpload(), to test their progress, their order and their cancellation. */
  holdUploads = false;
  /** The names of the files that fail, the others going in. */
  failing = new Set<string>();
  private pending: (() => void)[] = [];
  readonly docsUrl = '/api/docs';

  constructor(media: Medium[] = []) {
    this.media = media;
  }

  contentUrl(id: string) {
    return `/api/media/${id}/content`;
  }

  private answer<T>(value: T): Promise<Result<T>> {
    return Promise.resolve(this.failWith ? err(this.failWith) : ok(value));
  }

  listMedia(): Promise<Result<MediaList>> {
    return this.answer({ items: [...this.media], size: this.media.reduce((sum, m) => sum + m.size, 0), free: 9000 });
  }

  upload(file: File, options: UploadOptions, onProgress: (sent: number) => void,
         signal?: AbortSignal): Promise<Result<Medium>> {
    this.uploads.push({ file, options });
    return new Promise(resolve => {
      const done = () => {
        if (signal?.aborted) return;
        if (this.failWith) return resolve(err(this.failWith));
        if (this.failing.has(file.name)) return resolve(err(`cannot read ${file.name}`));
        onProgress(1);
        const kept = medium({ id: `id-${this.uploads.length}`, name: file.name, size: file.size, shown: options.play });
        this.media.push(kept);
        if (options.play) this.display = { ...BLACK, source: 'media', media: kept, name: kept.name, shown: true };
        resolve(ok(kept));
      };
      signal?.addEventListener('abort', () => resolve(err('stopped')), { once: true });
      onProgress(0.5);
      if (this.holdUploads) this.pending.push(done);
      else done();
    });
  }

  /** Lets the oldest upload waiting go in. */
  finishUpload() {
    this.pending.shift()?.();
  }

  removeMedium(id: string): Promise<Result<void>> {
    this.media = this.media.filter(m => m.id !== id);
    if (this.display.media?.id === id) this.display = BLACK;
    return this.answer(undefined);
  }

  removeAllMedia(): Promise<Result<void>> {
    this.media = [];
    this.display = BLACK;
    return this.answer(undefined);
  }

  getDisplay(): Promise<Result<Display>> {
    return this.answer(this.display);
  }

  showMedium(id: string): Promise<Result<Display>> {
    const found = this.media.find(m => m.id === id);
    if (!found) return Promise.resolve(err(`no quilt or video of the id '${id}'`));
    this.display = { ...BLACK, source: 'media', media: found, name: found.name, kind: found.kind, shown: true };
    return this.answer(this.display);
  }

  showTestPattern(): Promise<Result<Display>> {
    this.display = { ...BLACK, source: 'test pattern', name: 'numbers', kind: 'quilt', shown: true };
    return this.answer(this.display);
  }

  showBlack(): Promise<Result<void>> {
    this.display = BLACK;
    return this.answer(undefined);
  }

  getStatus(): Promise<Result<ServerStatus>> {
    return this.answer({ version: '0.1.0', screen: 'gl', looking_glass: { serial: 'LKG-PORT-00000', width: 1536, height: 2048 },
                         calibration_error: null, display: this.display });
  }
}
