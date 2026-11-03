import assert from 'node:assert/strict';
import test from 'node:test';
import { cursorQuotaState, isCursorAuthError } from './cursorQuota.js';

const account = { email: 'test@example.com' };

test('first launch and anonymous placeholders show zero with no remaining arc', () => {
  for (const data of [null, undefined, {}, { quota: { autoPercent: 0, apiPercent: 0 } },
    { authSource: 'none', quota: { cursorModelsPercent: 0 } },
    { demo: true, user: account, quota: { autoPercent: 0, apiPercent: 0 } }]) {
    const state = cursorQuotaState(data);
    assert.equal(state.connected, false);
    assert.equal(state.cursorRemainingPercent, 0);
    assert.equal(state.otherRemainingPercent, 0);
    assert.equal(state.cursorUsedPercent, 100);
    assert.equal(state.otherUsedPercent, 100);
  }
});

test('a signed-in account with no quota data still shows zero', () => {
  const state = cursorQuotaState({ user: account, quota: {} });
  assert.equal(state.connected, true);
  assert.equal(state.cursorRemainingPercent, 0);
  assert.equal(state.otherRemainingPercent, 0);
});

test('successful login restores actual quotas, including a genuinely unused allowance', () => {
  const data = { user: account, quota: { cursorModelsPercent: 0, otherModelsPercent: 63 } };
  const state = cursorQuotaState(data);
  assert.equal(state.connected, true);
  assert.equal(state.cursorRemainingPercent, 100);
  assert.equal(state.otherRemainingPercent, 37);
  assert.equal(state.cursorUsedPercent, 0);
  assert.equal(state.otherUsedPercent, 63);
  assert.equal(cursorQuotaState(data, true).cursorRemainingPercent, 0);
  assert.equal(cursorQuotaState(data, true).connected, false);
  assert.equal(cursorQuotaState(data).cursorRemainingPercent, 100);
});

test('local and web sessions support legacy quotas and independent pool limits', () => {
  for (const authSource of ['cursor-db', 'manual']) {
    const data = { authSource, quota: { autoPercent: 25, apiPercent: 80 } };
    assert.equal(cursorQuotaState(data).cursorRemainingPercent, 75);
    assert.equal(cursorQuotaState(data).otherRemainingPercent, 20);
    data.limits = { cursorModelsPercent: 10, otherModelsPercent: 60 };
    assert.equal(cursorQuotaState(data).cursorRemainingPercent, 90);
    assert.equal(cursorQuotaState(data).otherRemainingPercent, 40);
  }
});

test('invalid/missing quota fields cannot turn into a full allowance', () => {
  for (const value of [null, undefined, '', NaN, Infinity, 'unknown']) {
    const state = cursorQuotaState({ user: account, quota: { autoPercent: value, apiPercent: value } });
    assert.equal(state.cursorRemainingPercent, 0);
    assert.equal(state.otherRemainingPercent, 0);
  }
  assert.equal(cursorQuotaState({ user: account, quota: { autoPercent: 120 } }).cursorRemainingPercent, 0);
  assert.equal(cursorQuotaState({ user: account, quota: { autoPercent: -20 } }).cursorRemainingPercent, 100);
});

test('auth failures hide saved quota while temporary network failures do not log out', () => {
  const data = { user: account, quota: { autoPercent: 30, apiPercent: 50 } };
  for (const code of ['NO_SESSION', 'AUTH_EXPIRED']) {
    assert.equal(isCursorAuthError({ code }), true);
    const state = cursorQuotaState(data, isCursorAuthError({ code }));
    assert.equal(state.connected, false);
    assert.equal(state.cursorRemainingPercent, 0);
    assert.equal(state.otherRemainingPercent, 0);
  }
  assert.equal(isCursorAuthError(null), false);
  assert.equal(cursorQuotaState(data, isCursorAuthError({ code: 'API_ERROR' })).cursorRemainingPercent, 70);
});
