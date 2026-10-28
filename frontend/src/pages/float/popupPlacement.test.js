import assert from 'node:assert/strict';
import test from 'node:test';
import { popupPlacement } from './popupPlacement.js';

test('short Qoder popup follows the bottom icon with its tail centered', () => {
  const result = popupPlacement({ centerY: 260, popupHeight: 134, baseTop: 133, viewportHeight: 400 });
  assert.equal(result.offsetY, 60);
  assert.equal(result.tailTop, 67);
  assert.equal(133 + result.offsetY + result.tailTop, 260);
});

test('top and bottom icons keep tall popups within the window and avoid corners', () => {
  for (const centerY of [60, 200, 340]) {
    const result = popupPlacement({ centerY, popupHeight: 300, baseTop: 50, viewportHeight: 400 });
    const top = 50 + result.offsetY;
    assert.ok(top >= 18);
    assert.ok(top + 300 <= 382);
    assert.ok(result.tailTop >= 48 && result.tailTop <= 252);
    if (centerY >= top + 48 && centerY <= top + 252) {
      assert.equal(top + result.tailTop, centerY);
    }
  }
});

test('switching from tall popup to Qoder does not carry the old tail position', () => {
  const tall = popupPlacement({ centerY: 260, popupHeight: 300, baseTop: 50, viewportHeight: 400 });
  const short = popupPlacement({ centerY: 260, popupHeight: 134, baseTop: 133, viewportHeight: 400 });
  assert.ok(tall.tailTop > short.tailTop);
  assert.equal(short.tailTop, 134 / 2);
});

test('very short content still keeps the entire tail away from the corners', () => {
  const result = popupPlacement({ centerY: 390, popupHeight: 70, baseTop: 165, viewportHeight: 400 });
  assert.equal(result.tailTop, 35);
  assert.equal(165 + result.offsetY + 70, 382);
});
