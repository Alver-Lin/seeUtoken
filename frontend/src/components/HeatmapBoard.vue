<template>
  <section class="panel">
    <header class="panel-head heat-head">
      <div>
        <h3 class="panel-title">使用热力图</h3>
        <p class="heat-summary">
          <template v-if="summaryHasData">
            {{ year }} 年共使用
            <b>{{ formatMoney(modelValue?.cost || 0) }}</b>
            · {{ Number(modelValue?.calls || 0).toLocaleString('zh-CN') }} 次
          </template>
          <template v-else-if="loading">{{ year }} 年加载中…</template>
          <template v-else>这一年还没有使用记录</template>
        </p>
      </div>
      <div class="year-nav">
        <button
          type="button"
          class="year-nav-btn"
          aria-label="上一年"
          :disabled="year <= minYear || loading"
          @click="changeYear(-1)"
        >
          <LeftOutlined />
        </button>
        <span class="year-nav-label">{{ year }}年</span>
        <button
          type="button"
          class="year-nav-btn"
          aria-label="下一年"
          :disabled="year >= maxYear || loading"
          @click="changeYear(1)"
        >
          <RightOutlined />
        </button>
      </div>
    </header>

    <div class="contrib">
      <div class="contrib-months">
        <div v-for="m in months" :key="m.month" class="contrib-month">
          <div class="contrib-weeks">
            <div v-for="(week, wi) in m.weeks" :key="wi" class="contrib-col">
              <span
                v-for="(cell, ci) in week"
                :key="ci"
                class="contrib-cell"
                :class="cellClass(cell)"
                @mouseenter="showTip($event, cell)"
                @mouseleave="heatTip = null"
              />
            </div>
          </div>
          <div class="contrib-label">{{ m.month }}月</div>
        </div>
      </div>
    </div>

    <div
      v-if="heatTip"
      class="heat-tip"
      :style="{ left: `${heatTip.x}px`, top: `${heatTip.y}px` }"
    >
      {{ heatTip.text }}
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { LeftOutlined, RightOutlined } from '@ant-design/icons-vue';
import { seeUtoken } from '../bridge';
import { formatMoney } from '../utils/format';

const props = defineProps({
  modelValue: { type: Object, default: null },
});
const emit = defineEmits(['update:modelValue']);

const maxYear = new Date().getFullYear();
const minYear = maxYear - 5;
const year = ref(Number(props.modelValue?.year) || maxYear);
const loading = ref(false);
const heatTip = ref(null);

const months = computed(() => props.modelValue?.months || []);
const summaryHasData = computed(() => Number(props.modelValue?.calls || 0) > 0);

watch(
  () => props.modelValue?.year,
  (y) => {
    const n = Number(y);
    if (Number.isFinite(n) && n >= 1970 && n <= 2100) year.value = n;
  }
);

function cellClass(cell) {
  if (!cell) return 'pad';
  return `lv${Math.max(0, Math.min(4, Number(cell.level) || 0))}`;
}

function showTip(event, cell) {
  if (!cell) {
    heatTip.value = null;
    return;
  }
  const text = cell.level
    ? `${cell.date} · ${formatMoney(cell.cost)} · ${cell.calls} 次`
    : `${cell.date} · 无使用`;
  heatTip.value = { x: event.clientX, y: event.clientY, text };
}

async function changeYear(delta) {
  const next = year.value + delta;
  if (next < minYear || next > maxYear || loading.value) return;
  if (!Number.isFinite(next) || next < 1970 || next > 2100) return;
  loading.value = true;
  year.value = next;
  heatTip.value = null;
  try {
    const res = await seeUtoken.getHeatmap(next);
    if (res?.heatmap) emit('update:modelValue', res.heatmap);
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.panel {
  background: #fff;
  border: 1px solid #e7ebf0;
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

.heat-head {
  align-items: center;
}

.panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  color: #1f2937;
}

.heat-summary {
  margin: 6px 0 0;
  color: #4b5563;
  font-size: 13px;
}

.heat-summary b {
  color: #0f172a;
  font-size: 18px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.year-nav {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  height: 32px;
  padding: 2px;
  border: 1px solid #e8ecf1;
  border-radius: 10px;
  background: #f8fafc;
}

.year-nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #475569;
  cursor: pointer;
  line-height: 1;
}

.year-nav-btn:hover:not(:disabled) {
  background: #fff;
  color: #1677ff;
}

.year-nav-btn:disabled {
  color: #cbd5e1;
  cursor: not-allowed;
}

.year-nav-label {
  min-width: 64px;
  padding: 0 4px;
  color: #0f172a;
  font-size: 13px;
  font-weight: 650;
  line-height: 28px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.contrib {
  padding: 4px 18px 16px;
  overflow-x: auto;
}

.contrib-months {
  display: flex;
  gap: 14px;
  width: max-content;
  min-width: 100%;
  justify-content: space-between;
}

.contrib-month {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.contrib-weeks {
  display: flex;
  gap: 3px;
}

.contrib-col {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.contrib-cell {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  background: #ebedf0;
}

.contrib-cell.pad {
  background: transparent;
}

.contrib-cell.lv0 {
  background: #ebedf0;
}

.contrib-cell.lv1 {
  background: #d6e4ff;
}

.contrib-cell.lv2 {
  background: #8eb7ff;
}

.contrib-cell.lv3 {
  background: #1677ff;
}

.contrib-cell.lv4 {
  background: #0b4db3;
}

.contrib-cell:not(.pad) {
  cursor: pointer;
}

.contrib-label {
  color: #8b95a5;
  font-size: 12px;
  line-height: 1;
}

.heat-tip {
  position: fixed;
  z-index: 30;
  transform: translate(-50%, calc(-100% - 8px));
  padding: 6px 8px;
  border-radius: 6px;
  background: #1f2937;
  color: #fff;
  font-size: 12px;
  line-height: 1.4;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.18);
}
</style>
