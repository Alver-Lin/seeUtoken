import test from 'node:test';
import assert from 'node:assert/strict';
import { applyNativeMaterialClasses, normalizeNativeMaterialState } from './nativeMaterial.js';

test('Windows acrylic reaches the renderer without enabling macOS glass', () => {
  const classes = new Set();
  const root = { classList: { toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name) } };
  applyNativeMaterialClasses({ type: 'windows-acrylic', platform: 'win32' }, root);
  assert.ok(classes.has('native-windows-acrylic'));
  assert.ok(classes.has('native-windows'));
  assert.ok(!classes.has('native-liquid-glass'));
  assert.ok(!classes.has('native-material-opaque'));
  applyNativeMaterialClasses({ type: 'opaque', platform: 'win32', reducedTransparency: true }, root);
  assert.ok(!classes.has('native-windows-acrylic'));
  assert.ok(classes.has('native-reduced-transparency'));
  assert.ok(classes.has('native-material-opaque'));
  applyNativeMaterialClasses({ type: 'liquid-glass' }, root);
  assert.ok(classes.has('native-liquid-glass'));
  assert.ok(!classes.has('native-windows'));
});

test('unknown material types keep the existing transparent fallback', () => {
  assert.equal(normalizeNativeMaterialState({ type: 'unknown' }).type, 'transparent');
});
