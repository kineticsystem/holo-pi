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
  /** The video to play in a loop once this one has played once. */
  then: Medium | null;
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

export interface HoloPiApi {
  listMedia(signal?: AbortSignal): Promise<Result<MediaList>>;
  /** Uploads a file, reporting the share sent, 0 to 1; abort() through the signal stops it. */
  upload(file: File, options: UploadOptions, onProgress: (sent: number) => void,
         signal?: AbortSignal): Promise<Result<Medium>>;
  removeMedium(id: string): Promise<Result<void>>;
  removeAllMedia(): Promise<Result<void>>;
  getDisplay(signal?: AbortSignal): Promise<Result<Display>>;
  showMedium(id: string): Promise<Result<Display>>;
  showTestPattern(): Promise<Result<Display>>;
  showBlack(): Promise<Result<void>>;
  getStatus(signal?: AbortSignal): Promise<Result<ServerStatus>>;
  /** Where a medium's file downloads from. */
  contentUrl(id: string): string;
  /** Where the API's documentation is, Swagger UI. */
  readonly docsUrl: string;
}
