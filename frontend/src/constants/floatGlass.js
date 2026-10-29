/** 首页、详情大屏、侧边悬浮栏与弹窗的统一外观选项。 */
export const FLOAT_APPEARANCE_OPTIONS = [
  { value: 'light', label: '白天模式' },
  { value: 'dark', label: '黑夜模式' },
  { value: 'liquid', label: 'Liquid Glass（标准）' },
  { value: 'liquid-clear', label: 'Liquid Glass（通透）' },
  { value: 'liquid-light', label: 'Liquid Glass（白色标准）' },
  { value: 'liquid-light-clear', label: 'Liquid Glass（白色通透）' },
];

export const DEFAULT_FLOAT_GLASS_STYLE = 'light';

export function isLightAppearance(style) {
  return style === 'light' || style === 'liquid-light' || style === 'liquid-light-clear';
}

export function isLiquidMode(style) {
  return FLOAT_APPEARANCE_OPTIONS.some((option) => option.value === style && style.startsWith('liquid'));
}

export function isClearGlassStyle(style) {
  return style === 'liquid-clear' || style === 'liquid-light-clear';
}

export function normalizeFloatGlassStyle(value) {
  const v = String(value || '').trim();
  if (FLOAT_APPEARANCE_OPTIONS.some((o) => o.value === v)) return v;
  return DEFAULT_FLOAT_GLASS_STYLE;
}
