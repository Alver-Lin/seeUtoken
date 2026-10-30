import { nextTick, onMounted, onUnmounted, watch } from 'vue';
import { isClearGlassStyle, isLiquidMode } from '../../constants/floatGlass';
import {
  applyLiquidGlassBackdrop,
  clearLiquidGlassBackdrop,
  isChromiumBackdrop,
  upsertLiquidGlassFilter,
} from './liquidGlassEngine';

/** 原生 NSGlassEffectView 已接管整窗轮廓时，CSS/SVG 玻璃退场（token-monitor 分层） */
function nativeLiquidActive() {
  return ['liquid-glass', 'windows-acrylic', 'windows-translucent'].includes(window.__seeUtokenNativeMaterial?.type);
}

function observeSurface({ el, filterId, shape, getStyle, cssOnly = false }) {
  if (!el) return () => {};

  const rebuild = () => {
    if (!isLiquidMode(getStyle()) || nativeLiquidActive()) {
      clearLiquidGlassBackdrop(el);
      el.classList.remove('glass-liquid-active');
      return;
    }
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    if (w < 2 || h < 2) return;
    const br = parseFloat(getComputedStyle(el).borderRadius) || 16;
    if (!cssOnly) {
      upsertLiquidGlassFilter(filterId, w, h, br, shape);
      if (isChromiumBackdrop()) {
        applyLiquidGlassBackdrop(el, filterId);
      } else {
        clearLiquidGlassBackdrop(el);
      }
    } else {
      clearLiquidGlassBackdrop(el);
    }
    el.classList.add('glass-liquid-active');
  };

  const ro = new ResizeObserver(() => {
    window.requestAnimationFrame(rebuild);
  });
  ro.observe(el);
  rebuild();
  return () => {
    ro.disconnect();
    clearLiquidGlassBackdrop(el);
    el.classList.remove('glass-liquid-active');
  };
}

/**
 * @param {{ popRef: import('vue').Ref, railRef: import('vue').Ref, glassStyle: import('vue').Ref<string>, hoveredId: import('vue').Ref<string|null> }} opts
 */
export function useLiquidGlass({ popRef, railRef, glassStyle, hoveredId, nativeMaterialTick }) {
  const cleanups = [];

  const syncAll = async () => {
    await nextTick();
    cleanups.splice(0).forEach((fn) => fn());
    if (!isLiquidMode(glassStyle.value)) return;

    const railEl = railRef.value;
    if (railEl) {
      cleanups.push(
        observeSurface({
          el: railEl,
          filterId: 'seeu-lg-rail',
          shape: isClearGlassStyle(glassStyle.value) ? 'clear' : 'standard',
          getStyle: () => glassStyle.value,
        })
      );
    }
    if (hoveredId.value && popRef.value) {
      cleanups.push(
        observeSurface({
          el: popRef.value,
          filterId: 'seeu-lg-pop',
          shape: 'panel',
          getStyle: () => glassStyle.value,
          cssOnly: true,
        })
      );
    }
  };

  onMounted(() => {
    syncAll();
  });

  watch([glassStyle, popRef, railRef, hoveredId, nativeMaterialTick], syncAll);

  onUnmounted(() => {
    cleanups.splice(0).forEach((fn) => fn());
  });
}
