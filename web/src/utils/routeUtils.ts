// The page's addresses, after the #, so that the browser's back button and a reload work: the library, the play tab,
// #/play, and the grading page of a quilt, #/grade/<id>. Used by useRoute, and by what links to them.

export type Route = { page: 'library' } | { page: 'play' } | { page: 'grade'; id: string };

export function parseRoute(hash: string): Route {
  if (hash === '#/play') return { page: 'play' };
  const match = /^#\/grade\/([^/]+)$/.exec(hash);
  if (!match) return { page: 'library' };
  try {
    return { page: 'grade', id: decodeURIComponent(match[1]) };
  } catch {
    return { page: 'library' }; // Not one of our addresses.
  }
}

export function formatRoute(route: Route): string {
  if (route.page === 'play') return '#/play';
  return route.page === 'grade' ? `#/grade/${encodeURIComponent(route.id)}` : '#/';
}
