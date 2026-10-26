<template>
  <div class="donut-wrap" :style="{ width: size + 'px', height: size + 'px' }">
    <canvas ref="canvasRef" />
    <div v-if="$slots.center" class="donut-center">
      <slot name="center" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue';

const props = defineProps({
  segments: { type: Array, default: () => [] },
  size: { type: Number, default: 180 },
  cutout: { type: Number, default: 0.72 },
  track: { type: String, default: '#e5e7eb' },
});

const canvasRef = ref(null);

function draw() {
  const canvas = canvasRef.value;
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const size = props.size;
  canvas.width = size * dpr;
  canvas.height = size * dpr;
  canvas.style.width = `${size}px`;
  canvas.style.height = `${size}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const cx = size / 2;
  const cy = size / 2;
  const radius = size / 2 - 8;
  const inner = radius * props.cutout;
  ctx.clearRect(0, 0, size, size);

  const total = props.segments.reduce((s, seg) => s + Math.max(0, seg.value), 0) || 1;
  let angle = -Math.PI / 2;

  ctx.beginPath();
  ctx.arc(cx, cy, (radius + inner) / 2, 0, Math.PI * 2);
  ctx.strokeStyle = props.track;
  ctx.lineWidth = radius - inner;
  ctx.stroke();

  for (const seg of props.segments) {
    const sweep = (Math.max(0, seg.value) / total) * Math.PI * 2;
    if (sweep <= 0) continue;
    ctx.beginPath();
    ctx.arc(cx, cy, (radius + inner) / 2, angle, angle + sweep);
    ctx.strokeStyle = seg.color;
    ctx.lineWidth = radius - inner;
    ctx.stroke();
    angle += sweep;
  }
}

onMounted(draw);
watch(() => props.segments, draw, { deep: true });
</script>

<style scoped>
.donut-wrap {
  position: relative;
  margin: 0 auto;
}
.donut-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
</style>
