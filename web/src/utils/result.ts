// Errors as values: what can fail as expected (a request, a validation) returns a Result, with a message the user
// can read; throwing is for bugs.
export type Result<T, E = string> = { ok: true; value: T } | { ok: false; error: E };

export const ok = <T>(value: T): Result<T, never> => ({ ok: true, value });
export const err = <E>(error: E): Result<never, E> => ({ ok: false, error });
