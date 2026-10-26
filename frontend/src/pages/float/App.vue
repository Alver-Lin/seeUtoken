<template>
  <div class="root" :class="expanded ? 'expanded' : 'collapsed'">
    <button
      v-show="!expanded"
      class="ball"
      type="button"
      title="Cursor 用量 · 点击展开"
      @pointerdown="onDragStart"
      @pointermove="onDragMove"
      @pointerup="onDragEnd"
    >
      <svg class="ball-ring" viewBox="0 0 64 64">
        <circle class="track" cx="32" cy="32" r="26" />
        <circle
          class="value"
          cx="32"
          cy="32"
          r="26"
          :style="{ strokeDasharray: BALL_C, strokeDashoffset: ballOffset }"
        />
      </svg>
      <div class="ball-core">
        <span>◇</span>
        <b>{{ cursorPct }}%</b>
      </div>
    </button>

    <div v-show="expanded" class="panel">
      <div class="rail" @pointerdown="onDragStart" @pointermove="onDragMove" @pointerup="onDragEnd">
        <button
          v-for="svc in services"
          :key="svc.id"
          type="button"
          class="item"
          :class="{ active: svc.id === 'cursor' }"
          :title="svc.name"
        >
          <div class="ring">
            <svg viewBox="0 0 34 34">
              <circle class="ring-track" cx="17" cy="17" r="15" />
              <circle
                class="ring-value"
                cx="17"
                cy="17"
                r="15"
                :stroke="svc.color"
                :stroke-dasharray="RING_C"
                :stroke-dashoffset="ringOffset(percentFor(svc))"
              />
            </svg>
            <div class="icon" :style="{ background: svc.iconBg }">{{ svc.letter }}</div>
          </div>
          <span class="pct">{{ percentFor(svc) }}%</span>
        </button>
        <div class="divider" />
        <a-button shape="circle" size="small" class="open-btn" @click.stop="openDetail">详</a-button>
      </div>

      <div class="pop">
        <div class="pop-title"><span class="mark">◇</span> Cursor 用量</div>
        <div class="section">
          <div class="section-label">每月限额 · Cursor Models</div>
          <a-progress :percent="cursorPct" :show-info="false" stroke-color="#34d399" trail-color="rgba(255,255,255,.1)" />
          <div class="section-meta">
            <b>已用 {{ cursorPct }}%</b>
            <span>{{ resetText }}</span>
          </div>
        </div>
        <div class="section">
          <div class="section-label">每月限额 · Other Models</div>
          <a-progress :percent="otherPct" :show-info="false" stroke-color="#a78bfa" trail-color="rgba(255,255,255,.1)" />
          <div class="section-meta">
            <b>已用 {{ otherPct }}%</b>
            <span>{{ resetText }}</span>
          </div>
        </div>
        <a-space style="width: 100%; margin-top: 8px">
          <a-button block size="small" :loading="refreshing" @click="refresh">刷新</a-button>
          <a-button block size="small" type="primary" @click="openDetail">详情</a-button>
        </a-space>
        <div class="hint">{{ hint }}</div>
        <a-button type="link" block class="collapse" @click="collapse">收起为悬浮球</a-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { seeUtoken } from '../../bridge';

const RING_C = 2 * Math.PI * 15;
const BALL_C = 2 * Math.PI * 26;

const services = [
  { id: 'openai', name: 'ChatGPT', color: '#22c55e', iconBg: '#10a37f', letter: 'G', demoPercent: 37 },
  { id: 'claude', name: 'Claude', color: '#14b8a6', iconBg: '#d97757', letter: 'C', demoPercent: 13 },
  { id: 'cursor', name: 'Cursor', color: '#a78bfa', iconBg: '#111111', letter: '◇', live: true },
  { id: 'gemini', name: 'Gemini', color: '#f472b6', iconBg: '#4285f4', letter: 'G', demoPercent: 1 },
  { id: 'kimi', name: 'Kimi', color: '#60a5fa', iconBg: '#3b82f6', letter: 'K', demoPercent: 0 },
  { id: 'other', name: 'Other', color: '#94a3b8', iconBg: '#475569', letter: '·', demoPercent: 0 },
];

const expanded = ref(false);
const usageData = ref(null);
const refreshing = ref(false);
let unsub = null;
let drag = null;
let moved = false;

const cursorPct = computed(() => {
  if (!usageData.value) return 0;
  return Math.round(
    Number(usageData.value.limits?.cursorModelsPercent ?? usageData.value.quota?.usedPercent ?? 0) || 0
  );
});
const otherPct = computed(() => Math.round(Number(usageData.value?.limits?.otherModelsPercent ?? 0) || 0));
const ballOffset = computed(() => BALL_C * (1 - Math.min(100, cursorPct.value) / 100));
const resetText = computed(() => {
  const ts = usageData.value?.cycle?.resetAt;
  if (!ts) return '—';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '—';
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')} 重置`;
});
const hint = computed(() => {
  if (!usageData.value) return '正在加载…';
  if (usageData.value.demo) return '演示数据：登录 Cursor IDE 后自动读取真实额度';
  const remain = usageData.value.quota?.remaining;
  return remain != null ? `剩余 $${Number(remain).toFixed(2)} · 点击详情查看完整报表` : '';
});

function percentFor(svc) {
  return svc.live ? cursorPct.value : Math.round(svc.demoPercent || 0);
}
function ringOffset(p) {
  return RING_C * (1 - Math.max(0, Math.min(100, p)) / 100);
}

async function setExpanded(next) {
  expanded.value = next;
  await seeUtoken.setFloatExpanded(next);
}

function onDragStart(e) {
  if (e.button !== 0) return;
  moved = false;
  drag = { x: e.screenX, y: e.screenY };
  e.currentTarget.setPointerCapture?.(e.pointerId);
}
function onDragMove(e) {
  if (!drag) return;
  const dx = e.screenX - drag.x;
  const dy = e.screenY - drag.y;
  if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
  if (moved) {
    seeUtoken.moveFloatBy(dx, dy);
    drag = { x: e.screenX, y: e.screenY };
  }
}
function onDragEnd() {
  const wasMoved = moved;
  drag = null;
  if (!wasMoved && !expanded.value) setExpanded(true);
}

function collapse() {
  setExpanded(false);
}
function openDetail() {
  seeUtoken.openDashboardDetail();
}
async function refresh() {
  refreshing.value = true;
  try {
    const res = await seeUtoken.refreshUsage();
    usageData.value = res?.data || null;
  } finally {
    refreshing.value = false;
  }
}

onMounted(async () => {
  document.documentElement.style.background = 'transparent';
  document.body.style.background = 'transparent';
  const settings = await seeUtoken.getSettings();
  expanded.value = settings?.floatCollapsed === false;
  try {
    const res = await seeUtoken.getUsage(false);
    usageData.value = res?.data || null;
  } catch (_) {}
  unsub = seeUtoken.onUsageUpdated((payload) => {
    usageData.value = payload?.data || null;
  });
});

onUnmounted(() => {
  if (unsub) unsub();
});
</script>

<style>
html, body, #app {
  margin: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: transparent !important;
}
</style>

<style scoped>
.root { width: 100%; height: 100%; position: relative; user-select: none; font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }
.ball {
  position: absolute; inset: 4px; border: 0; padding: 0; border-radius: 50%;
  background: transparent; cursor: grab;
}
.ball:active { cursor: grabbing; }
.ball-ring { position: absolute; inset: 0; width: 100%; height: 100%; transform: rotate(-90deg); filter: drop-shadow(0 6px 16px rgba(0,0,0,.35)); }
.ball-ring .track { fill: none; stroke: rgba(255,255,255,.18); stroke-width: 4; }
.ball-ring .value { fill: none; stroke: #a78bfa; stroke-width: 4; stroke-linecap: round; transition: stroke-dashoffset .4s ease; }
.ball-core {
  position: absolute; inset: 8px; border-radius: 50%;
  background: linear-gradient(160deg, #2a2a32, #121218);
  border: 1px solid rgba(255,255,255,.1);
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1px; color: #fff;
}
.ball-core b { font-size: 10px; }
.panel {
  position: absolute; inset: 0; display: flex; justify-content: flex-end; gap: 10px; padding: 8px;
}
.rail {
  width: 56px; border-radius: 999px; background: rgba(18,18,22,.92);
  border: 1px solid rgba(255,255,255,.08); box-shadow: 0 8px 32px rgba(0,0,0,.4);
  display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 12px 8px; cursor: grab;
}
.item { border: 0; background: transparent; color: #fff; display: flex; flex-direction: column; align-items: center; gap: 3px; cursor: pointer; position: relative; font: inherit; }
.ring { width: 34px; height: 34px; position: relative; display: grid; place-items: center; }
.ring svg { position: absolute; inset: 0; width: 100%; height: 100%; transform: rotate(-90deg); }
.ring-track { fill: none; stroke: rgba(255,255,255,.12); stroke-width: 2.5; }
.ring-value { fill: none; stroke-width: 2.5; stroke-linecap: round; }
.icon { width: 18px; height: 18px; border-radius: 5px; display: grid; place-items: center; font-size: 10px; font-weight: 700; position: relative; z-index: 1; color: #fff; }
.pct { font-size: 10px; font-weight: 600; color: rgba(255,255,255,.75); }
.item.active::after {
  content: ""; position: absolute; right: -14px; top: 10px;
  border-style: solid; border-width: 6px 0 6px 8px;
  border-color: transparent transparent transparent rgba(28,28,34,.96);
}
.divider { width: 22px; height: 1px; background: rgba(255,255,255,.1); }
.open-btn { background: rgba(255,255,255,.08) !important; color: #fff !important; border-color: rgba(255,255,255,.12) !important; }
.pop {
  width: 280px; align-self: center; padding: 16px 16px 12px; border-radius: 16px;
  background: rgba(28,28,34,.96); border: 1px solid rgba(255,255,255,.08);
  box-shadow: 0 16px 48px rgba(0,0,0,.45); color: #fff;
}
.pop-title { display: flex; align-items: center; gap: 8px; font-weight: 700; margin-bottom: 14px; }
.mark { width: 20px; height: 20px; border-radius: 6px; background: #111; display: grid; place-items: center; font-size: 11px; }
.section { margin-bottom: 12px; }
.section-label { font-size: 12px; color: rgba(255,255,255,.55); margin-bottom: 8px; }
.section-meta { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; color: rgba(255,255,255,.45); }
.section-meta b { color: #fff; }
.hint { margin-top: 8px; font-size: 11px; color: rgba(255,255,255,.4); line-height: 1.4; min-height: 16px; }
.collapse { color: rgba(255,255,255,.55) !important; margin-top: 4px; }
</style>
