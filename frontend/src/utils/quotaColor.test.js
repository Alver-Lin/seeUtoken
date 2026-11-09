import assert from 'node:assert/strict';
import test from 'node:test';
import { QUOTA_REMAIN_COLORS, remainingQuotaColor } from './quotaColor.js';

test('remaining quota colors follow the 90 / 50 / 10 thresholds', () => {
  assert.equal(remainingQuotaColor(100), QUOTA_REMAIN_COLORS.full);
  assert.equal(remainingQuotaColor(90), QUOTA_REMAIN_COLORS.full);
  assert.equal(remainingQuotaColor(89.4), QUOTA_REMAIN_COLORS.high);
  assert.equal(remainingQuotaColor(50), QUOTA_REMAIN_COLORS.high);
  assert.equal(remainingQuotaColor(49.4), QUOTA_REMAIN_COLORS.mid);
  assert.equal(remainingQuotaColor(10), QUOTA_REMAIN_COLORS.mid);
  assert.equal(remainingQuotaColor(9.4), QUOTA_REMAIN_COLORS.low);
  assert.equal(remainingQuotaColor(0), QUOTA_REMAIN_COLORS.low);
});

test('invalid remaining values fall back to the low band', () => {
  for (const value of [null, undefined, '', NaN, Infinity, -5]) {
    assert.equal(remainingQuotaColor(value), QUOTA_REMAIN_COLORS.low);
  }
});
