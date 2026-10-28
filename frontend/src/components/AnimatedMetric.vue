<template>
  <span class="anim-metric" :class="{ bump: pulsing }">{{ text }}</span>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue';
import { formatTokens, formatTokensExact } from '../utils/format';

const props = defineProps({
  value: { type: Number, default: 0 },
  mode: { type: String, default: 'tokens' }, // tokens | exact | percent | raw
  suffix: { type: String, default: '' },
});

const shown = ref(0);
const pulsing = ref(false);
let frame = 0;
let pulseTimer = null;

function formatValue(n) {
  const v = Math.max(0, Number(n) || 0);
  if (props.mode === 'percent') return `${v}${props.suffix || '%'}`;
  if (props.mode === 'tokens') return formatTokens(v);
  if (props.mode === 'exact') return formatTokensExact(v);
  return `${v}${props.suffix || ''}`;
}

const text = computed(() => formatValue(shown.value));

function animateTo(target) {
  const to = Math.max(0, Number(target) || 0);
  const from = shown.value;
  cancelAnimationFrame(frame);
  if (from === to) {
    shown.value = to;
    return;
  }
  pulsing.value = true;
  if (pulseTimer) window.clearTimeout(pulseTimer);
  const t0 = performance.now();
  const dur = 520;
  const step = (t) => {
    const p = Math.min(1, (t - t0) / dur);
    const eased = 1 - (1 - p) ** 3;
    shown.value = Math.round(from + (to - from) * eased);
    if (p < 1) {
      frame = requestAnimationFrame(step);
    } else {
      shown.value = to;
      pulseTimer = window.setTimeout(() => {
        pulsing.value = false;
        pulseTimer = null;
      }, 200);
    }
  };
  frame = requestAnimationFrame(step);
}

watch(
  () => props.value,
  (v) => animateTo(v),
  { immediate: true }
);

onUnmounted(() => {
  cancelAnimationFrame(frame);
  if (pulseTimer) window.clearTimeout(pulseTimer);
});
</script>

<style scoped>
.anim-metric {
  display: inline-block;
  font-variant-numeric: tabular-nums;
  transition: transform 0.2s ease, color 0.2s ease, opacity 0.2s ease;
}
.anim-metric.bump {
  transform: scale(1.08);
  color: #fff;
}
</style>
