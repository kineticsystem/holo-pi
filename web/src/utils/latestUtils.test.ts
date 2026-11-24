import { expect, test } from 'vitest';
import { makeLatest } from './latestUtils';

function setUp() {
  const sent: number[] = [];
  const answers: (() => void)[] = [];
  const latest = makeLatest<number>(value => {
    sent.push(value);
    return new Promise(resolve => answers.push(resolve));
  });
  async function answer() {
    answers.shift()?.();
    await Promise.resolve();
    await Promise.resolve();
  }
  return { sent, latest: latest.send, settled: latest.settled, answer };
}

test('the first value goes at once', () => {
  const { sent, latest } = setUp();
  latest(1);
  expect(sent).toEqual([1]);
});

test('while one is on its way, only the newest goes next', async () => {
  const { sent, latest, answer } = setUp();
  [1, 2, 3, 4].forEach(latest);
  expect(sent).toEqual([1]);
  await answer();
  expect(sent).toEqual([1, 4]);
  await answer();
  expect(sent).toEqual([1, 4]);
});

test('it is settled once the last value is answered', async () => {
  const { latest, settled, answer } = setUp();
  await settled(); // Nothing on its way.
  latest(1);
  latest(2);
  let done = false;
  void settled().then(() => { done = true; });
  await answer();
  expect(done).toBe(false);
  await answer();
  await settled();
  expect(done).toBe(true);
});

test('a value after the last answer goes at once again', async () => {
  const { sent, latest, answer } = setUp();
  latest(1);
  await answer();
  latest(2);
  expect(sent).toEqual([1, 2]);
});
