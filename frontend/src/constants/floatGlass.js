/** 首页、详情大屏、侧边悬浮栏与弹窗的统一外观选项。 */
export const FLOAT_APPEARANCE_OPTIONS = [
  { value: 'light', label: '白天模式' },
  { value: 'dark', label: '黑夜模式' },
  { value: 'liquid', label: 'Liquid Glass（标准）' },
  { value: 'liquid-clear', label: 'Liquid Glass（通透）' },
];

export const DEFAULT_FLOAT_GLASS_STYLE = 'light';

export function normalizeFloatGlassStyle(value) {
  const v = String(value || '').trim();
  if (FLOAT_APPEARANCE_OPTIONS.some((o) => o.value === v)) return v;
  return DEFAULT_FLOAT_GLASS_STYLE;
}
