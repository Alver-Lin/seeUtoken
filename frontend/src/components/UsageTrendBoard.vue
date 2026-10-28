<template>
  <section class="panel">
    <header class="panel-head trend-head">
      <div>
        <h3 class="panel-title">使用趋势</h3>
        <p class="trend-sub">{{ rangeLabel }}</p>
      </div>
      <div v-if="peakTokens > 0" class="trend-peak" :title="peakExactTitle">
        峰值 <b>{{ formatTokens(peakTokens) }}</b>
      </div>
    </header>

    <div v-if="chart.points.length" class="trend-body">
      <div
        ref="trendWrapRef"
        class="trend-chart-wrap"
        @mousemove="onMove"
        @mouseleave="hover = null"
      >
        <svg
          ref="trendSvgRef"
          class="trend-svg"
          :viewBox="`0 0 ${chart.width} ${chart.height}`"
          preserveAspectRatio="none"
          role="img"
          aria-label="Token 使用趋势"
        >
          <defs>
            <linearGradient :id="gradId" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#4d9ff5" stop-opacity="0.2" />
              <stop offset="100%" stop-color="#4d9ff5" stop-opacity="0" />
            </linearGradient>
          </defs>
          <path
            v-if="chart.area"
            :d="chart.area"
            :fill="`url(#${gradId})`"
            stroke="none"
          />
          <path v-if="chart.line" class="trend-line" :d="chart.line" />
        </svg>
        <div v-if="hover" class="trend-hover-layer" aria-hidden="true">
          <div class="trend-vline" :style="{ left: `${hover.px}px` }" />
          <div class="trend-dot" :style="{ left: `${hover.px}px`, top: `${hover.py}px` }" />
          <div
            class="trend-tip"
            :style="{ left: `${hover.tipLeft}px`, top: `${hover.tipTop}px` }"
          >
            {{ hover.tip }}
          </div>
        </div>
      </div>
      <div class="trend-axis">
        <span v-for="(lbl, i) in chart.labels" :key="i">{{ lbl }}</span>
      </div>
    </div>
    <p v-else class="block-empty">最近暂无 Token 使用趋势</p>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue';
import { formatTokens, formatTokensExact } from '../utils/format';
import { tokenBasisLabel } from '../utils/tokenAccounting';

const props = defineProps({
  heatmap: { type: Object, default: null },
});

const WINDOW_DAYS = 90;
const gradId = `trend-fill-${Math.random().toString(36).slice(2, 9)}`;
const hover = ref(null);
const trendSvgRef = ref(null);
const trendWrapRef = ref(null);

function localDateKey(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function collectDailyPoints(hm) {
  if (!hm) return [];
  const out = [];
  if (hm.days && typeof hm.days === 'object') {
    for (const [date, v] of Object.entries(hm.days)) {
      out.push({ date, tokens: Number(v?.tokens) || 0 });
    }
  } else {
    for (const m of hm.months || []) {
      for (const week of m.weeks || []) {
        for (const cell of week || []) {
          if (cell?.date) {
            out.push({ date: cell.date, tokens: Number(cell.tokens) || 0 });
          }
        }
      }
    }
  }
  return out.sort((a, b) => a.date.localeCompare(b.date));
}

const series = computed(() => {
  const all = collectDailyPoints(props.heatmap);
  const end = new Date();
  end.setHours(0, 0, 0, 0);
  const start = new Date(end);
  start.setDate(start.getDate() - (WINDOW_DAYS - 1));
  const tokenByDate = new Map(all.map((p) => [p.date, p.tokens]));
  const out = [];
  const cur = new Date(start);
  while (cur <= end) {
    const key = localDateKey(cur);
    out.push({ date: key, tokens: tokenByDate.get(key) || 0 });
    cur.setDate(cur.getDate() + 1);
  }
  return out.some((p) => p.tokens > 0) ? out : [];
});

const peakTokens = computed(() =>
  series.value.length ? Math.max(...series.value.map((p) => p.tokens)) : 0
);

const peakExactTitle = computed(() =>
  peakTokens.value > 0 ? `${formatTokensExact(peakTokens.value)} Token` : ''
);

const rangeLabel = computed(() => {
  const s = series.value;
  const basis = tokenBasisLabel(props.heatmap?.includeCachedTokens);
  if (!s.length) return `近 ${WINDOW_DAYS} 日 · ${basis}`;
  return `${formatAxisDate(s[0].date)} – ${formatAxisDate(s[s.length - 1].date)} · ${basis}`;
});

function formatAxisDate(key) {
  if (!key) return '—';
  const d = new Date(`${key}T12:00:00`);
  if (Number.isNaN(d.getTime())) return key;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function buildLinearPath(coords) {
  if (!coords.length) return '';
  return coords
    .map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x.toFixed(2)} ${c.y.toFixed(2)}`)
    .join(' ');
}

/** Soft line: low-tension cubic with Y clamped to avoid overshoot / self-intersecting fill. */
function buildSoftLinePath(coords, yMin, yMax) {
  if (!coords.length) return '';
  if (coords.length <= 2) return buildLinearPath(coords);
  const tension = 0.22;
  let d = `M ${coords[0].x.toFixed(2)} ${coords[0].y.toFixed(2)}`;
  for (let i = 0; i < coords.length - 1; i += 1) {
    const p0 = coords[i - 1] || coords[i];
    const p1 = coords[i];
    const p2 = coords[i + 1];
    const p3 = coords[i + 2] || p2;
    let cp1x = p1.x + (p2.x - p0.x) * tension;
    let cp1y = p1.y + (p2.y - p0.y) * tension;
    let cp2x = p2.x - (p3.x - p1.x) * tension;
    let cp2y = p2.y - (p3.y - p1.y) * tension;
    const segLo = Math.min(p1.y, p2.y);
    const segHi = Math.max(p1.y, p2.y);
    cp1y = Math.min(segHi, Math.max(segLo, cp1y));
    cp2y = Math.min(segHi, Math.max(segLo, cp2y));
    cp1y = Math.min(yMax, Math.max(yMin, cp1y));
    cp2y = Math.min(yMax, Math.max(yMin, cp2y));
    d += ` C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)}, ${cp2x.toFixed(2)} ${cp2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`;
  }
  return d;
}

const chart = computed(() => {
  const pts = series.value;
  const width = 640;
  const height = 160;
  const padX = 8;
  const padTop = 8;
  const padBottom = 22;
  if (!pts.length) {
    return { width, height, points: [], line: '', area: '', labels: [] };
  }

  const maxY = Math.max(...pts.map((p) => p.tokens), 1);
  const innerW = width - padX * 2;
  const innerH = height - padTop - padBottom;
  const coords = pts.map((p, i) => {
    const x = padX + (pts.length <= 1 ? innerW / 2 : (i / (pts.length - 1)) * innerW);
    const y = padTop + innerH - (p.tokens / maxY) * innerH;
    return { ...p, x, y };
  });

  const baseY = padTop + innerH;
  const line = buildSoftLinePath(coords, padTop, baseY);
  const areaLinear = buildLinearPath(coords);
  const area = `${areaLinear} L ${coords[coords.length - 1].x.toFixed(2)} ${baseY} L ${coords[0].x.toFixed(2)} ${baseY} Z`;

  const labelIdx =
    coords.length <= 2
      ? coords.map((_, i) => i)
      : [0, Math.floor((coords.length - 1) / 2), coords.length - 1];
  const labels = [...new Set(labelIdx)].map((i) => formatAxisDate(coords[i].date));

  return { width, height, points: coords, line, area, labels, maxY };
});

function viewBoxToWrap(svgEl, wrapEl, vx, vy) {
  const vb = chart.value;
  const svgRect = svgEl.getBoundingClientRect();
  const wrapRect = wrapEl.getBoundingClientRect();
  const px = (vx / vb.width) * svgRect.width + (svgRect.left - wrapRect.left);
  const py = (vy / vb.height) * svgRect.height + (svgRect.top - wrapRect.top);
  return { px, py, wrapRect };
}

function nearestIndexByViewX(pts, vx) {
  let idx = 0;
  let best = Infinity;
  for (let i = 0; i < pts.length; i += 1) {
    const d = Math.abs(pts[i].x - vx);
    if (d < best) {
      best = d;
      idx = i;
    }
  }
  return idx;
}

function formatTipDate(key) {
  if (!key) return '—';
  const d = new Date(`${key}T12:00:00`);
  if (Number.isNaN(d.getTime())) return key;
  const y = d.getFullYear();
  const m = d.getMonth() + 1;
  const day = d.getDate();
  return `${y}/${m}/${day}`;
}

function onMove(event) {
  const pts = chart.value.points;
  const svgEl = trendSvgRef.value;
  const wrapEl = trendWrapRef.value;
  const vb = chart.value;
  if (!pts.length || !svgEl || !wrapEl) return;

  const svgRect = svgEl.getBoundingClientRect();
  const vx = Math.min(vb.width, Math.max(0, ((event.clientX - svgRect.left) / svgRect.width) * vb.width));
  const idx = nearestIndexByViewX(pts, vx);
  const p = pts[idx];
  const { px, py, wrapRect } = viewBoxToWrap(svgEl, wrapEl, p.x, p.y);

  const tipLeft = Math.min(Math.max(px, 56), wrapRect.width - 56);
  const tipTop = Math.max(6, py - 36);

  hover.value = {
    px,
    py,
    tipLeft,
    tipTop,
    tip: `${formatTipDate(p.date)} · ${formatTokensExact(p.tokens)} Token`,
  };
}
</script>

<style scoped>
.panel {
  background: var(--sut-surface, #fff);
  border: 1px solid var(--sut-border, #e7ebf0);
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 14px 18px 8px;
}

.trend-head {
  align-items: center;
}

.panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  color: var(--sut-text, #1f2937);
}

.trend-sub {
  margin: 6px 0 0;
  color: var(--sut-secondary, #64748b);
  font-size: 12px;
}

.trend-peak {
  color: var(--sut-secondary, #64748b);
  font-size: 12px;
  white-space: nowrap;
}

.trend-peak b {
  color: var(--sut-text, #0f172a);
  font-size: 14px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.trend-body {
  position: relative;
  padding: 0 18px 14px;
}

.trend-chart-wrap {
  position: relative;
}

.trend-svg {
  display: block;
  width: 100%;
  height: 168px;
  border-radius: 10px;
  background: linear-gradient(180deg, var(--sut-inset, #f7faff) 0%, var(--sut-inset, #f4f7fb) 100%);
}

.trend-hover-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.trend-vline {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 0;
  border-left: 1px dashed var(--sut-muted, #94a3b8);
  transform: translateX(-0.5px);
}

.trend-line {
  fill: none;
  stroke: #3b93f0;
  stroke-width: 1.5;
  stroke-linejoin: round;
  stroke-linecap: round;
}

.trend-dot {
  position: absolute;
  width: 8px;
  height: 8px;
  margin: -4px 0 0 -4px;
  border-radius: 50%;
  background: #3b93f0;
  border: 2px solid var(--sut-surface, #fff);
  box-shadow: 0 0 0 1px rgba(59, 147, 240, 0.25);
}

.trend-axis {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  padding: 0 4px;
  color: var(--sut-muted, #94a3b8);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.trend-tip {
  position: absolute;
  right: auto;
  width: max-content;
  max-width: 280px;
  transform: translateX(-50%);
  padding: 5px 10px;
  border-radius: 6px;
  background: #1f2937;
  color: #fff;
  font-size: 11px;
  line-height: 1.35;
  pointer-events: none;
  white-space: nowrap;
  z-index: 2;
  box-sizing: border-box;
}

.block-empty {
  margin: 0;
  padding: 28px 18px 32px;
  color: var(--sut-muted, #94a3b8);
  text-align: center;
}
</style>
