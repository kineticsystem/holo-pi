// Sends the latest of many values, one at a time: while one is on its way, only the newest of those that came since
// waits, and goes next. For a slider, which changes many times while one request is answered. Used by useGrade.

export type Latest<T> = {
  send: (value: T) => void;
  /** Resolves once nothing is on its way nor waiting. */
  settled: () => Promise<void>;
};

/** Sends the values given to it through `send`, which must not throw, one at a time, skipping those overtaken. */
export function makeLatest<T>(send: (value: T) => Promise<void>): Latest<T> {
  let running: Promise<void> | null = null;
  let waiting: { value: T } | null = null;

  async function run(value: T) {
    let next: { value: T } | null = { value };
    while (next) {
      waiting = null;
      await send(next.value);
      next = waiting;
    }
    running = null;
  }

  return {
    send(value) {
      if (running) waiting = { value };
      else running = run(value);
    },
    settled: () => running ?? Promise.resolve(),
  };
}
