import assert from 'node:assert/strict';
import test from 'node:test';
import { setImmediate } from 'node:timers/promises';
import { createShapeSender } from './shapeSender.js';

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

test('rapid switches keep one native request in flight and send the final layout', async () => {
  const first = deferred();
  const calls = [];
  const sender = createShapeSender(async (shape) => {
    calls.push(shape.id);
    if (shape.id === 'cursor') await first.promise;
  });
  sender.push({ id: 'cursor' });
  sender.push({ id: 'codex' });
  sender.push({ id: 'qoder' });
  sender.push({ id: 'codex-final' });
  assert.deepEqual(calls, ['cursor']);
  first.resolve();
  await setImmediate();
  assert.deepEqual(calls, ['cursor', 'codex-final']);
  sender.push({ id: 'codex-final' });
  await setImmediate();
  assert.equal(calls.length, 2);
});

test('failed requests do not suppress a retry of the same geometry', async () => {
  let attempts = 0;
  const sender = createShapeSender(async () => {
    if (++attempts === 1) throw new Error('bridge unavailable');
  });
  sender.push({ id: 'cursor' });
  await setImmediate();
  sender.push({ id: 'cursor' });
  await setImmediate();
  assert.equal(attempts, 2);
});

test('unmount drops pending geometry even if an older request completes later', async () => {
  const first = deferred();
  const calls = [];
  const sender = createShapeSender(async (shape) => {
    calls.push(shape.id);
    await first.promise;
  });
  sender.push({ id: 'cursor' });
  sender.push({ id: 'qoder' });
  sender.dispose();
  first.resolve();
  await setImmediate();
  sender.push({ id: 'codex' });
  assert.deepEqual(calls, ['cursor']);
});
