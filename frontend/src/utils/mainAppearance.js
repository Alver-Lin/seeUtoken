import { computed, defineComponent, h, ref } from 'vue';
import { ConfigProvider, theme } from 'ant-design-vue';
import { seeUtoken } from '../bridge';
import { normalizeFloatGlassStyle } from '../constants/floatGlass';
import { applyNativeMaterialClasses, normalizeNativeMaterialState } from './nativeMaterial';

// Shared by the home page and both dashboards. Keep the persisted setting compatible.
export const mainAppearance = ref(normalizeFloatGlassStyle(window.__seeUtokenFloatSettings?.floatGlassStyle));
const nativeMaterial = ref(normalizeNativeMaterialState(window.__seeUtokenNativeMaterial));
export const mainIsDark = computed(() => mainAppearance.value !== 'light');
const chartTrack = computed(() => mainIsDark.value ? '#364356' : '#e6ebf2');

export function applyMainAppearance(settings) {
  if (!settings || !('floatGlassStyle' in settings)) return;
  mainAppearance.value = normalizeFloatGlassStyle(settings.floatGlassStyle);
  window.__seeUtokenFloatSettings = { ...window.__seeUtokenFloatSettings, floatGlassStyle: mainAppearance.value };
  updateRoot();
}

function updateRoot() {
  const root = document.documentElement;
  root.dataset.sutAppearance = mainAppearance.value;
  root.style.removeProperty('background-color');
  root.style.colorScheme = mainIsDark.value ? 'dark' : 'light';
  applyNativeMaterialClasses(nativeMaterial.value);
}

export function mountWithAppearance(app) {
  window.__seeUtokenApplyFloatSettings = applyMainAppearance;
  window.__seeUtokenApplyNativeMaterial = (state) => {
    nativeMaterial.value = normalizeNativeMaterialState(state);
    window.__seeUtokenNativeMaterial = nativeMaterial.value;
    updateRoot();
  };
  updateRoot();
  const readSettings = () => seeUtoken.getSettings().then(applyMainAppearance).catch(() => {});
  readSettings();
  window.addEventListener('focus', readSettings);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) readSettings();
  });
  app.provide('sutChartTrack', chartTrack);
  app.mount('#app');
}

export function appearanceRoot(component) {
  return defineComponent({
    setup() {
      const config = computed(() => {
        const glass = mainAppearance.value.startsWith('liquid') &&
          !nativeMaterial.value.reducedTransparency && nativeMaterial.value.type !== 'opaque';
        const clear = mainAppearance.value === 'liquid-clear';
        return {
          algorithm: mainIsDark.value ? theme.darkAlgorithm : theme.defaultAlgorithm,
          token: {
            colorPrimary: mainIsDark.value ? '#579dff' : '#1677ff',
            colorBgBase: mainIsDark.value ? '#161e2b' : '#ffffff',
            colorBgContainer: glass ? (clear ? 'rgba(83, 106, 139, 0.16)' : 'rgba(68, 88, 116, 0.28)') : mainIsDark.value ? '#222d3e' : '#ffffff',
            colorBgElevated: glass ? (clear ? 'rgba(22, 33, 49, 0.42)' : 'rgba(24, 35, 51, 0.76)') : mainIsDark.value ? '#263245' : '#ffffff',
            colorBgMask: glass ? (clear ? 'rgba(4, 10, 20, 0.18)' : 'rgba(4, 10, 20, 0.28)') : 'rgba(0, 0, 0, 0.45)',
            colorText: mainIsDark.value ? '#edf2fa' : '#1f2937',
            colorTextSecondary: mainIsDark.value ? '#aebbd0' : '#64748b',
            colorBorder: mainIsDark.value ? '#46536a' : '#dce3eb',
            borderRadius: 8,
          },
        };
      });
      return () => h(ConfigProvider, { theme: config.value }, { default: () => h(component) });
    },
  });
}
