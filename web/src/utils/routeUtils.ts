// The page's addresses, after the #, so that the browser's back button and a reload work: the library, and the grading
// page of a quilt, #/grade/<id>. Used by useRoute, and by what links to the grading page.

export type Route = { page: 'library' } | { page: 'grade'; id: string };

export function parseRoute(hash: string): Route {
  const match = /^#\/grade\/([^/]+)$/.exec(hash);
  if (!match) return { page: 'library' };
  try {
    return { page: 'grade', id: decodeURIComponent(match[1]) };
  } catch {
    return { page: 'library' }; // Not one of our addresses.
  }
}

export function formatRoute(route: Route): string {
  return route.page === 'grade' ? `#/grade/${encodeURIComponent(route.id)}` : '#/';
}
