// The page's one store: the library's media, what the Looking Glass shows, and the server's status, as the server
// last said. Every panel reads it, and changes it through these actions only.
import type { Display, MediaList, Medium, ServerStatus } from '../services/HoloPiApi';

export type HoloPiState = {
  media: Medium[] | null; // null until the first list arrives
  size: number;
  free: number;
  display: Display | null;
  status: ServerStatus | null;
};

export type HoloPiAction =
  | { type: 'mediaListed'; list: MediaList }
  | { type: 'mediumUploaded'; medium: Medium }
  | { type: 'mediumRemoved'; id: string }
  | { type: 'mediaOrdered'; ids: string[] }
  | { type: 'allMediaRemoved' }
  | { type: 'displayRead'; display: Display }
  | { type: 'statusRead'; status: ServerStatus };

export const initialState: HoloPiState = { media: null, size: 0, free: 0, display: null, status: null };

export function holoPiReducer(state: HoloPiState, action: HoloPiAction): HoloPiState {
  switch (action.type) {
    case 'mediaListed':
      return { ...state, media: action.list.items, size: action.list.size, free: action.list.free };
    case 'mediumUploaded': {
      // An upload of a name the library has replaces it, with the same id.
      const others = (state.media ?? []).filter(medium => medium.id !== action.medium.id);
      const before = (state.media ?? []).find(medium => medium.id === action.medium.id);
      const size = state.size - (before?.size ?? 0) + action.medium.size;
      const media = before
        ? (state.media ?? []).map(medium => (medium.id === action.medium.id ? action.medium : medium))
        : [...others, action.medium];
      return { ...state, media, size, free: Math.max(0, state.free - (size - state.size)) };
    }
    case 'mediumRemoved': {
      const removed = (state.media ?? []).find(medium => medium.id === action.id);
      const media = (state.media ?? []).filter(medium => medium.id !== action.id);
      return { ...state, media, size: state.size - (removed?.size ?? 0), free: state.free + (removed?.size ?? 0) };
    }
    case 'mediaOrdered': {
      // The media in the order of the ids; those not among them, e.g. an upload meanwhile, after them.
      const media = state.media ?? [];
      const place = new Map(action.ids.map((id, index) => [id, index]));
      const ordered = [...media].sort((a, b) => (place.get(a.id) ?? Infinity) - (place.get(b.id) ?? Infinity));
      return { ...state, media: ordered };
    }
    case 'allMediaRemoved':
      return { ...state, media: [], size: 0, free: state.free + state.size };
    case 'displayRead':
      return { ...state, display: action.display };
    case 'statusRead':
      return { ...state, status: action.status, display: action.status.display };
  }
}

/** The id of the medium the Looking Glass shows, or null: from the display, so the list never needs a copy. */
export function selectShownId(state: HoloPiState): string | null {
  return state.display?.source === 'media' ? (state.display.media?.id ?? null) : null;
}
