<template>
  <div class="ring" :style="{ width: size + 'px', height: size + 'px' }">
    <svg :viewBox="`0 0 ${size} ${size}`" aria-hidden="true">
      <circle
        class="track"
        :cx="half"
        :cy="half"
        :r="radius"
        :stroke-width="stroke"
        fill="none"
      />
      <circle
        class="value"
        :cx="half"
        :cy="half"
        :r="radius"
        :stroke-width="stroke"
        fill="none"
        stroke-linecap="round"
        :stroke-dasharray="circumference"
        :stroke-dashoffset="offset"
        :transform="`rotate(-90 ${half} ${half})`"
      />
    </svg>
    <div class="label">{{ display }}%</div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  percent: { type: Number, default: 0 },
  size: { type: Number, default: 72 },
  stroke: { type: Number, default: 7 },
});

const half = computed(() => props.size / 2);
const radius = computed(() => (props.size - props.stroke) / 2);
const circumference = computed(() => 2 * Math.PI * radius.value);
const clamped = computed(() => Math.max(0, Math.min(100, Number(props.percent) || 0)));
const offset = computed(() => circumference.value * (1 - clamped.value / 100));
const display = computed(() => Math.round(clamped.value));
</script>

<style scoped>
.ring {
  position: relative;
  flex-shrink: 0;
}
svg {
  display: block;
  width: 100%;
  height: 100%;
}
.track {
  stroke: var(--sut-track, #edf2f7);
}
.value {
  stroke: #1877f2;
  transition: stroke-dashoffset 0.35s ease;
}
.label {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font-size: 15px;
  font-weight: 700;
  color: var(--sut-text, #1a202c);
  font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC',
    'Microsoft YaHei', sans-serif;
  letter-spacing: -0.02em;
}
</style>
