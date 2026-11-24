// The real client of HoloPi's API, over HTTP, on the server that serves the page: fetch for the requests, and
// XMLHttpRequest for the uploads, as fetch cannot say how much of a request is sent.
import { err, ok, type Result } from '../utils/result';
import type { Display, Grade, GradeParameter, HoloPiApi, MediaList, Medium, ServerStatus, UploadOptions } from './HoloPiApi';

/** What an answer that is not ok says: the server's {"error": ...}, or else its status. */
async function problem(response: Response): Promise<string> {
  const body = await response.json().catch(() => ({}));
  return typeof body?.error === 'string' ? body.error : `${response.status} ${response.statusText}`;
}

async function request<T>(url: string, init: RequestInit = {}): Promise<Result<T>> {
  try {
    const response = await fetch(url, init);
    if (!response.ok) return err(await problem(response));
    if (response.status === 204) return ok(undefined as T);
    return ok((await response.json()) as T);
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return err('stopped');
    return err(`cannot reach the server: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

/** A grade as the server has it: its values and `enabled`, side by side. */
type FlatGrade = Record<string, number | boolean>;

function toGrade({ enabled, ...values }: FlatGrade): Grade {
  return { enabled: enabled !== false, values: values as Record<string, number> };
}

async function map<T, U>(result: Promise<Result<T>>, change: (value: T) => U): Promise<Result<U>> {
  const settled = await result;
  return settled.ok ? ok(change(settled.value)) : settled;
}

export function makeHttpHoloPiApi(baseUrl = ''): HoloPiApi {
  const api = `${baseUrl}/api`;
  return {
    docsUrl: `${api}/docs`,
    contentUrl: id => `${api}/media/${encodeURIComponent(id)}/content`,
    listMedia: signal => request<MediaList>(`${api}/media`, { signal }),
    orderMedia: ids => request<MediaList>(`${api}/media/order`, json('PUT', { ids })),
    removeMedium: id => request<void>(`${api}/media/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    removeAllMedia: () => request<void>(`${api}/media`, { method: 'DELETE' }),
    getDisplay: signal => request<Display>(`${api}/display`, { signal }),
    showMedium: id => request<Display>(`${api}/display`, json('PUT', { media_id: id })),
    showTestPattern: () => request<Display>(`${api}/display`, json('PUT', { test_pattern: true })),
    showBlack: () => request<void>(`${api}/display`, { method: 'DELETE' }),
    listGradeParameters: signal =>
      map(request<{ items: GradeParameter[] }>(`${api}/grade-parameters`, { signal }), list => list.items),
    getGrade: (id, signal) => map(request<FlatGrade>(`${api}/media/${encodeURIComponent(id)}/grade`, { signal }), toGrade),
    setGrade: (id, grade) =>
      map(request<FlatGrade>(`${api}/media/${encodeURIComponent(id)}/grade`,
                             json('PUT', { ...grade.values, enabled: grade.enabled })), () => undefined),
    getStatus: signal => request<ServerStatus>(`${api}/status`, { signal }),
    upload: (file: File, options: UploadOptions, onProgress, signal) =>
      new Promise<Result<Medium>>(resolve => {
        const form = new FormData();
        form.append('file', file, file.name);
        if (options.columns !== null && options.rows !== null) {
          form.append('columns', String(options.columns));
          form.append('rows', String(options.rows));
        }
        form.append('reverse', String(options.reverse));
        form.append('play', String(options.play));
        const xhr = new XMLHttpRequest();
        xhr.open('POST', `${api}/media`);
        xhr.responseType = 'json';
        xhr.upload.onprogress = event => {
          if (event.lengthComputable) onProgress(event.loaded / event.total);
        };
        xhr.onload = () => {
          if (xhr.status === 200 || xhr.status === 201) {
            resolve(ok(xhr.response as Medium));
          } else {
            const error = (xhr.response as { error?: unknown } | null)?.error;
            resolve(err(typeof error === 'string' ? error : `${xhr.status} ${xhr.statusText}`));
          }
        };
        xhr.onerror = () => resolve(err('cannot reach the server'));
        xhr.onabort = () => resolve(err('stopped'));
        signal?.addEventListener('abort', () => xhr.abort(), { once: true });
        xhr.send(form);
      }),
  };
}
