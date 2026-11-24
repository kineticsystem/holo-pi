// A HoloPi API in memory, for the tests: a library, a display, and failures on request.
import type { Display, Grade, GradeParameter, HoloPiApi, MediaList, Medium, ServerStatus, UploadOptions } from '../services/HoloPiApi';
import { err, ok, type Result } from '../utils/result';

export function medium(fields: Partial<Medium> = {}): Medium {
  return {
    id: 'a1', name: 'helix_qs8x6a0.75.mp4', kind: 'quilt video', size: 1000, uploaded: '2026-11-17T11:45:02+00:00',
    width: 3360, height: 3360, columns: 8, rows: 6, reverse: false, fps: 24, frames: 480, duration: 20,
    codec: 'hevc', warning: null, grade: null, shown: false, ...fields,
  };
}

function parameter(id: string, section: string, minimum = -100, maximum = 100, decimals = 0): GradeParameter {
  const label = id[0].toUpperCase() + id.slice(1);
  return { id, label, section, description: `What the ${id} does.`, minimum, maximum, default: 0, decimals };
}

export const PARAMETERS = [
  parameter('saturation', 'Color'), parameter('exposure', 'Light', -5, 5, 2), parameter('contrast', 'Light'),
  parameter('sharpness', 'Effects', 0, 150),
];

const BLACK: Display = {
  source: null, media: null, name: null, kind: null, reverse: false, shown: false, shown_on: null, error: null,
  frame_rate: null, decoder: null, warning: null,
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
  /** The ids of the media whose removal fails, the others going. */
  refusing = new Set<string>();
  private pending: (() => void)[] = [];
  /** The ids showMedium() was asked for, in order. */
  shows: string[] = [];
  /** Shows wait for finishShow(), to test what is asked while the screen changes. */
  holdShows = false;
  private pendingShows: (() => void)[] = [];
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

  /** The orders orderMedia() was asked for. */
  orders: string[][] = [];

  orderMedia(ids: string[]): Promise<Result<MediaList>> {
    this.orders.push(ids);
    if (this.failWith) return Promise.resolve(err(this.failWith));
    const known = new Set(this.media.map(m => m.id));
    if (ids.length !== known.size || !ids.every(id => known.has(id))) {
      return Promise.resolve(err("give each of the library's ids once"));
    }
    this.media = ids.map(id => this.media.find(m => m.id === id)!);
    return this.listMedia();
  }

  renameMedium(id: string, name: string): Promise<Result<Medium>> {
    if (this.failWith) return Promise.resolve(err(this.failWith));
    if (this.media.some(m => m.name === name && m.id !== id)) return Promise.resolve(err(`the library has another ${name}`));
    this.media = this.media.map(m => (m.id === id ? { ...m, name } : m));
    const renamed = this.media.find(m => m.id === id)!;
    if (this.display.media?.id === id) this.display = { ...this.display, media: renamed, name };
    return Promise.resolve(ok(renamed));
  }

  removeMedium(id: string): Promise<Result<void>> {
    if (this.refusing.has(id)) return Promise.resolve(err(`cannot remove ${id}`));
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
    this.shows.push(id);
    const show = () => {
      const found = this.media.find(m => m.id === id);
      if (!found) return Promise.resolve(err(`no quilt or video of the id '${id}'`));
      this.display = { ...BLACK, source: 'media', media: found, name: found.name, kind: found.kind, shown: true };
      return this.answer(this.display);
    };
    if (!this.holdShows) return show();
    return new Promise(resolve => this.pendingShows.push(() => void show().then(resolve)));
  }

  /** Lets the oldest show waiting reach the screen. */
  finishShow() {
    this.pendingShows.shift()?.();
  }

  showTestPattern(): Promise<Result<Display>> {
    this.display = { ...BLACK, source: 'test pattern', name: 'numbers', kind: 'quilt', shown: true };
    return this.answer(this.display);
  }

  showBlack(): Promise<Result<void>> {
    this.display = BLACK;
    return this.answer(undefined);
  }

  /** The grades kept, by their quilts' ids, and those asked for, in order. */
  grades = new Map<string, Grade>();
  gradesSet: Grade[] = [];
  /** Grades wait for finishGrade(), to test what a slider sends while the screen draws. */
  holdGrades = false;
  private pendingGrades: (() => void)[] = [];
  screen = 'gl';

  listGradeParameters(): Promise<Result<GradeParameter[]>> {
    return this.answer(PARAMETERS);
  }

  getGrade(id: string): Promise<Result<Grade>> {
    return this.answer(this.grades.get(id) ?? { enabled: true, values: {} });
  }

  setGrade(id: string, grade: Grade): Promise<Result<void>> {
    this.gradesSet.push(grade);
    const set = () => {
      this.grades.set(id, grade);
      return this.answer(undefined);
    };
    if (!this.holdGrades) return set();
    return new Promise(resolve => this.pendingGrades.push(() => void set().then(resolve)));
  }

  /** Lets the oldest grade waiting be drawn. */
  finishGrade() {
    this.pendingGrades.shift()?.();
  }

  /** The saves asked for: the quilt's id, and its grade at that moment. */
  saves: { id: string; grade: Grade | undefined }[] = [];
  /** Saves wait for finishSave(). */
  holdSaves = false;
  private pendingSaves: (() => void)[] = [];

  saveGraded(id: string): Promise<Result<Medium>> {
    this.saves.push({ id, grade: this.grades.get(id) });
    const saved = medium({ id: `saved-${this.saves.length}`, name: 'helix-graded_qs8x6a0.75.png', kind: 'quilt' });
    const save = () => {
      if (!this.failWith) this.media.push(saved);
      return this.answer(saved);
    };
    if (!this.holdSaves) return save();
    return new Promise(resolve => this.pendingSaves.push(() => void save().then(resolve)));
  }

  /** Lets the oldest save waiting end. */
  finishSave() {
    this.pendingSaves.shift()?.();
  }

  getStatus(): Promise<Result<ServerStatus>> {
    return this.answer({ version: '0.1.0', screen: this.screen, looking_glass: { serial: 'LKG-PORT-00000', width: 1536, height: 2048 },
                         calibration_error: null, display: this.display });
  }
}
