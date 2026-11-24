// HoloPi's HTTP API, as the page uses it: the types of its answers and the interface of its client. The page only
// knows this interface; App gives it the real client, the tests a fake. See the server's own documentation on
// /api/docs.
import type { Result } from '../utils/result';

export type MediaKind = 'quilt' | 'quilt video' | 'hologram video';

/** A quilt or a video kept in the server's library. */
export type Medium = {
  id: string;
  name: string;
  kind: MediaKind;
  size: number;
  uploaded: string;
  width: number;
  height: number;
  columns: number | null;
  rows: number | null;
  reverse: boolean;
  fps: number | null;
  frames: number | null;
  duration: number | null;
  codec: string | null;
  warning: string | null;
  shown: boolean;
};

export type MediaList = { items: Medium[]; size: number; free: number };

/** What the Looking Glass shows. */
export type Display = {
  source: 'media' | 'test pattern' | 'default' | null;
  media: Medium | null;
  name: string | null;
  kind: MediaKind | null;
  reverse: boolean;
  shown: boolean;
  shown_on: string | null;
  error: string | null;
  frame_rate: number | null;
  decoder: 'hardware' | 'software' | null;
  warning: string | null;
};

/** How a quilt's light and colours are changed when it is shown: the values by their parameters' ids, those left out
 * at their defaults. Not enabled, the quilt is shown as uploaded, and the values are kept. */
export type Grade = { enabled: boolean; values: Record<string, number> };

/** One value of a grade: a slider of the grading page. */
export type GradeParameter = {
  id: string;
  label: string;
  section: string;
  description: string;
  minimum: number;
  maximum: number;
  default: number;
  decimals: number;
};

export type ServerStatus = {
  version: string;
  screen: string;
  looking_glass: { serial: string; width: number; height: number } | null;
  calibration_error: string | null;
  display: Display;
};

export type UploadOptions = {
  /** The quilt's layout, when its name does not say, e.g. 8 and 6; both or neither. */
  columns: number | null;
  rows: number | null;
  /** Its views in the other order. */
  reverse: boolean;
  /** Show it at once, too. */
  play: boolean;
};

/** What the page asks of an upload: its layout only. It always shows the first file and keeps the views' order. */
export type UploadLayout = Pick<UploadOptions, 'columns' | 'rows'>;

export interface HoloPiApi {
  listMedia(signal?: AbortSignal): Promise<Result<MediaList>>;
  /** Uploads a file, reporting the share sent, 0 to 1; abort() through the signal stops it. */
  upload(file: File, options: UploadOptions, onProgress: (sent: number) => void,
         signal?: AbortSignal): Promise<Result<Medium>>;
  /** Puts the library in the order of `ids`, each of its ids once; answers the list as it is now. */
  orderMedia(ids: string[]): Promise<Result<MediaList>>;
  /** Gives a medium another name; answers it as it is now, its extension added if the name lacks it. */
  renameMedium(id: string, name: string): Promise<Result<Medium>>;
  removeMedium(id: string): Promise<Result<void>>;
  removeAllMedia(): Promise<Result<void>>;
  getDisplay(signal?: AbortSignal): Promise<Result<Display>>;
  showMedium(id: string): Promise<Result<Display>>;
  showTestPattern(): Promise<Result<Display>>;
  showBlack(): Promise<Result<void>>;
  /** The tools of a grade, section by section, in the order to show them. */
  listGradeParameters(signal?: AbortSignal): Promise<Result<GradeParameter[]>>;
  getGrade(id: string, signal?: AbortSignal): Promise<Result<Grade>>;
  /** Replaces a quilt's grade; if the Looking Glass shows the quilt, it answers once it is drawn with it. */
  setGrade(id: string, grade: Grade): Promise<Result<void>>;
  /** Keeps a quilt with its grade as a new quilt, which it answers; the quilt and what is shown stay. */
  saveGraded(id: string): Promise<Result<Medium>>;
  getStatus(signal?: AbortSignal): Promise<Result<ServerStatus>>;
  /** Where a medium's file downloads from. */
  contentUrl(id: string): string;
  /** Where the API's documentation is, Swagger UI. */
  readonly docsUrl: string;
}
