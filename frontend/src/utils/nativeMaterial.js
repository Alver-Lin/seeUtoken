/** 与 token-monitor glassRendering.js / nativeMaterial 状态对齐 */

const DEFAULT = {
  type: 'transparent',
  reducedTransparency: false,
  highContrast: false,
  fallbackReason: null,
  liquidGlassSupported: false,
};

export function normalizeNativeMaterialState(value) {
  const types = new Set(['liquid-glass', 'vibrancy', 'transparent', 'opaque', 'windows-acrylic', 'windows-translucent']);
  const type = types.has(value?.type) ? value.type : 'transparent';
  return {
    platform: value?.platform === 'win32' ? 'win32' : null,
    floatStyle: typeof value?.floatStyle === 'string' ? value.floatStyle : null,
    type,
    reducedTransparency: value?.reducedTransparency === true,
    highContrast: value?.highContrast === true,
    fallbackReason:
      value?.fallbackReason == null ? null : String(value.fallbackReason),
    liquidGlassSupported: value?.liquidGlassSupported === true,
  };
}

export function usesNativeLiquidGlass(state) {
  return normalizeNativeMaterialState(state).type === 'liquid-glass';
}

export function usesNativeVibrancy(state) {
  return normalizeNativeMaterialState(state).type === 'vibrancy';
}

export function applyNativeMaterialClasses(state, root = document.documentElement) {
  const material = normalizeNativeMaterialState(state);
  if (!root) return material;
  root.classList.toggle('native-liquid-glass', material.type === 'liquid-glass');
  root.classList.toggle('native-vibrancy', material.type === 'vibrancy');
  root.classList.toggle('native-windows', material.platform === 'win32');
  root.classList.toggle('native-windows-acrylic', material.type === 'windows-acrylic');
  root.classList.toggle('native-windows-glass', ['windows-acrylic', 'windows-translucent'].includes(material.type));
  root.classList.toggle('native-material-opaque', material.type === 'opaque');
  root.classList.toggle('native-reduced-transparency', material.reducedTransparency);
  root.classList.toggle('native-high-contrast', material.highContrast);
  return material;
}

export function readBootstrapNativeMaterial() {
  const raw = typeof window !== 'undefined' ? window.__seeUtokenNativeMaterial : null;
  return normalizeNativeMaterialState(raw || DEFAULT);
}

export function installNativeMaterialHook(onChange) {
  if (typeof window === 'undefined') return;
  window.__seeUtokenApplyNativeMaterial = (state) => {
    const normalized = normalizeNativeMaterialState(state);
    // 轮询路径（syncNativeMaterialFromApi）直接调本函数，也要回写快照，
    // 否则 useLiquidGlass/glassShape 读到的 window 快照与类名不一致
    window.__seeUtokenNativeMaterial = normalized;
    onChange(normalized);
    applyNativeMaterialClasses(normalized);
  };
  const boot = readBootstrapNativeMaterial();
  onChange(boot);
  applyNativeMaterialClasses(boot);
}
