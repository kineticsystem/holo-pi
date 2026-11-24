// Sends the latest of many values, one at a time: while one is on its way, only the newest of those that came since
// waits, and goes next. For a slider, which changes many times while one request is answered. Used by useGrade.

/** Sends the values given to it through `send`, which must not throw, one at a time, skipping those overtaken. */
export function makeLatest<T>(send: (value: T) => Promise<void>): (value: T) => void {
  let busy = false;
  let waiting: { value: T } | null = null;

  async function run(value: T) {
    busy = true;
    let next: { value: T } | null = { value };
    while (next) {
      waiting = null;
      await send(next.value);
      next = waiting;
    }
    busy = false;
  }

  return value => {
    if (busy) waiting = { value };
    else void run(value);
  };
}
