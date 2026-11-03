import assert from 'node:assert/strict';
import test from 'node:test';
import { localDateKey, weeklyUsage } from './weeklyUsage.js';

test('seven local calendar days cross month boundaries and highlight today', () => {
  const chart = weeklyUsage([], null, new Date(2026, 10, 2, 18));
  assert.equal(chart.monthLabel, '10月-11月');
  assert.deepEqual(chart.days.map(day => day.day), [27, 28, 29, 30, 31, 1, 2]);
  assert.deepEqual(chart.days.map(day => day.weekday), ['二', '三', '四', '五', '六', '日', '一']);
  assert.deepEqual(chart.days.map(day => day.today), [false, false, false, false, false, false, true]);
});

test('bar heights use real daily tokens and the latest today total', () => {
  const chart = weeklyUsage([
    { date: '2026-10-27', tokens: 100 }, { date: '2026-10-28', tokens: 20 },
    { date: '2026-11-02', tokens: 5 },
  ], 10, new Date(2026, 10, 2));
  assert.deepEqual(chart.days.map(day => day.tokens), [100, 20, null, null, null, null, 10]);
  assert.deepEqual(chart.days.map(day => day.height), [100, 20, 0, 0, 0, 0, 10]);
});

test('zero is a known total and missing values stay unknown without fabricated bars', () => {
  const chart = weeklyUsage([{ date: '2026-11-01', tokens: 0 }], 0, new Date(2026, 10, 2));
  assert.equal(chart.monthLabel, '10月-11月');
  assert.equal(chart.days[0].tokens, null);
  assert.equal(chart.days[5].tokens, 0);
  assert.equal(chart.days[6].tokens, 0);
  assert.ok(chart.days.every(day => day.height === 0));
});

test('new years, leap days, and a same-month window retain correct dates', () => {
  assert.equal(weeklyUsage([], null, new Date(2026, 0, 2)).days[0].date, '2025-12-27');
  assert.equal(weeklyUsage([], null, new Date(2024, 2, 1)).days[5].date, '2024-02-29');
  assert.equal(weeklyUsage([], null, new Date(2026, 10, 20)).monthLabel, '11月');
  assert.equal(localDateKey(new Date(2026, 0, 2, 23, 59)), '2026-01-02');
});
