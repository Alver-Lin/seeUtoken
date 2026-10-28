<template>
  <div class="root expanded" :class="{ 'edge-left': dockState.edge === 'left', 'edge-collapsed': dockState.collapsed }" :data-glass="floatGlassStyle">
    <button v-if="dockState.collapsed && !dockState.nativeHandle" ref="edgeTabRef" class="edge-tab" type="button" aria-label="展开侧边用量栏" @click="seeUtoken.revealFloatDock()" />
    <div v-show="!dockState.collapsed || dockState.nativeHandle" class="panel">
      <div class="dock" @mouseenter="clearHoverTimer" @mouseleave="onDockLeave">
        <div ref="popAnchorRef" class="pop-anchor" :class="{ visible: !!hoveredId }" :style="{ top: `${popOffsetY}px` }">
          <div
            v-if="hoveredId"
            ref="popCardRef"
            class="pop glass-surface glass-surface--pop"
            :class="{ 'pop-muted': hoveredId === 'qoder' }"
          >
          <template v-if="hoveredId === 'cursor'">
          <div class="pop-head">
            <div class="pop-title">
              <img class="pop-logo" :src="PROVIDER_META.cursor.logo" alt="" />
              Cursor
            </div>
            <span v-if="usageData?.user?.membership" class="pop-plan" :title="usageData.user.membership">{{ usageData.user.membership }}</span>
            <button
              type="button"
              class="pop-refresh"
              title="刷新"
              :disabled="refreshing"
              @click.stop="refresh"
            >
              <ReloadOutlined :spin="refreshing" />
            </button>
          </div>
          <div class="pop-donuts">
            <div class="pop-donut">
              <DonutChart
                :size="108"
                :cutout="0.72"
                :segments="cursorDonutSegments"
                :track="donutTrack"
              >
                <template #center>
                  <div class="donut-pct">
                    <AnimatedMetric :value="cursorRemainPct" mode="percent" />
                  </div>
                  <div class="donut-cap">剩余</div>
                </template>
              </DonutChart>
              <div class="pop-donut-name">Cursor 模型</div>
            </div>
            <div class="pop-donut">
              <DonutChart
                :size="108"
                :cutout="0.72"
                :segments="otherDonutSegments"
                :track="donutTrack"
              >
                <template #center>
                  <div class="donut-pct">
                    <AnimatedMetric :value="otherRemainPct" mode="percent" />
                  </div>
                  <div class="donut-cap">剩余</div>
                </template>
              </DonutChart>
              <div class="pop-donut-name">其余模型</div>
            </div>
          </div>
          <div class="pop-total-row" :title="tokenBasisLabel(usageData?.includeCachedTokens)">
            <div class="pop-total-label">今日 TOKEN</div>
            <AnimatedMetric class="pop-total-value" :value="todayTokenTotal" mode="exact" />
          </div>
          <div class="pop-reset">{{ resetText }}</div>
          </template>
          <template v-else-if="hoveredId === 'codex'">
            <div class="pop-head">
              <div class="pop-title"><img class="pop-logo codex" :src="PROVIDER_META.codex.logo" alt="" />Codex</div>
              <span v-if="codexData?.user?.plan" class="pop-plan" :title="codexData.user.plan">{{ codexData.user.plan }}</span>
              <button type="button" class="pop-refresh" title="刷新 Codex" :disabled="codexLoading || codexData?.syncing" @click.stop="refreshCodex(true)"><ReloadOutlined :spin="codexLoading || codexData?.syncing" /></button>
            </div>
            <div class="pop-donuts">
              <div v-for="(item, i) in codexWindows" :key="item.id" class="pop-donut">
                <DonutChart :size="108" :cutout="0.72" :segments="quotaSegments(item, i, 'transparent')" :track="donutTrack" rounded-caps>
                  <template #center><div class="donut-pct">{{ quotaText(item) }}</div><div class="donut-cap">{{ item.stale ? '待更新' : '剩余' }}</div></template>
                </DonutChart>
                <div class="pop-donut-name">{{ item.label }}</div>
              </div>
            </div>
            <div class="pop-total-row" :title="`${tokenBasisLabel(codexData?.includeCachedTokens)}；本机 Codex 记录`"><div class="pop-total-label">今日 TOKEN</div><AnimatedMetric class="pop-total-value" :value="codexData?.usageTokens?.today || 0" mode="exact" /></div>
            <div class="pop-reset codex-resets">
              <div v-for="item in codexWindows" :key="item.id" class="codex-reset-row">
                <span>{{ item.label }}重置</span>
                <span class="codex-reset-time">{{ codexResetTime(item) }}</span>
              </div>
            </div>
          </template>
          <template v-else>
          <div class="pop-title">
            <img class="pop-logo" :class="hoveredId" :src="hoveredMeta?.logo" alt="" />
            {{ hoveredMeta?.name }}
          </div>
          <p class="pop-status">未接入</p>
          <p class="pop-desc">额度接入即将支持，请在模型额度首页查看该面板。</p>
          </template>
          </div>
          <span
            v-if="hoveredId"
            class="pop-tail"
            aria-hidden="true"
            :style="popTailStyle"
          />
        </div>

        <div
          ref="railRef"
          class="rail glass-surface glass-surface--rail"
          @pointerdown="onDragStart"
          @pointermove="onDragMove"
          @pointerup="onDragEnd"
          @pointercancel="onDragEnd"
          @lostpointercapture="onDragEnd"
        >
        <button
          v-for="svc in visibleServices"
          :key="svc.id"
          :ref="setItemRef(svc.id)"
          type="button"
          class="item"
          :data-provider-id="svc.id"
          :title="itemTitle(svc)"
          @pointerenter="onItemEnter(svc.id)"
          @dblclick.stop="onItemDblClick(svc)"
        >
          <div class="ring" :class="{ 'provider-busy': (svc.id === 'cursor' && cursorBusy) || (svc.id === 'codex' && codexBusy) }">
            <svg viewBox="0 0 38 38">
              <circle class="ring-track" cx="19" cy="19" :r="RING_R" />
              <circle
                class="ring-value"
                cx="19"
                cy="19"
                :r="RING_R"
                :stroke="svc.live ? svc.color : donutTrack"
                :stroke-dasharray="RING_C"
                :stroke-dashoffset="ringOffset(percentFor(svc))"
              />
            </svg>
            <div class="icon" :class="svc.id">
              <img v-if="svc.logo" class="icon-img" :src="svc.logo" alt="" />
            </div>
          </div>
          <span class="pct" :class="{ muted: !svc.live }">{{ percentLabel(svc) }}</span>
        </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { ReloadOutlined } from '@ant-design/icons-vue';
import { seeUtoken } from '../../bridge';
import DonutChart from '../../components/DonutChart.vue';
import AnimatedMetric from '../../components/AnimatedMetric.vue';
import cursorLogo from '../../assets/brand/cursor-logo-white.svg';
import codexLogo from '../../assets/brand/codex-logo.svg';
import qoderLogo from '../../assets/brand/qoder-logo.svg';
import { normalizeFloatGlassStyle } from '../../constants/floatGlass';
import './glass.css';
import './solid.css';
import { useLiquidGlass } from './useLiquidGlass';
import { useNativeGlassShape } from './glassShape';
import { installNativeMaterialHook } from '../../utils/nativeMaterial';
import { quotaText, quotaSegments, useCodexUsage } from '../../utils/codex';
import { popupPlacement } from './popupPlacement';
import { createRailDrag } from './railDrag';
import { tokenBasisLabel } from '../../utils/tokenAccounting';

const RING_R = 17;
const RING_C = 2 * Math.PI * RING_R;
const BALL_C = 2 * Math.PI * 26;

const DEFAULT_PANEL_TYPES = ['cursor', 'codex', 'qoder'];

const PROVIDER_META = {
  cursor: { id: 'cursor', name: 'Cursor', color: '#34d399', logo: cursorLogo, live: true },
  codex: { id: 'codex', name: 'Codex', color: '#10a37f', logo: codexLogo, live: true },
  qoder: { id: 'qoder', name: 'Qoder', color: '#12c26a', logo: qoderLogo, live: false },
};

const expanded = ref(true);
const usageData = ref(null);
const refreshing = ref(false);
const bootstrapSettings = window.__seeUtokenFloatSettings;
let includeCachedTokens = !!bootstrapSettings?.includeCachedTokens;
const panelTypes = ref(uniquePanelTypes(bootstrapSettings?.panels));
const hoveredId = ref(null);
const dockState = ref(window.__seeUtokenFloatDock || { edge: null, collapsed: false });
const edgeTabRef = ref(null);

function applyDockState(state) {
  clearHoverTimer();
  if (state.collapsed || state.edge !== dockState.value.edge) hoveredId.value = null;
  dockState.value = state;
  nextTick(updatePopTail);
}
const { data: codexData, loading: codexLoading, refresh: refreshCodex } = useCodexUsage();
const codexWindows = computed(() => codexData.value?.windows || [{ id: 'primary', label: '短期额度' }, { id: 'secondary', label: '长期额度' }]);

function codexResetTime(item) {
  if (!item?.resetsAt || item.stale) return '等待更新';
  const date = new Date(item.resetsAt);
  if (Number.isNaN(date.getTime())) return '等待更新';
  const time = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
  return `${date.getMonth() + 1}月${date.getDate()}日 ${time}`;
}
const floatGlassStyle = ref(normalizeFloatGlassStyle(bootstrapSettings?.floatGlassStyle));
const donutTrack = computed(() => floatGlassStyle.value === 'light' ? '#e2e8f0' : 'rgba(255,255,255,.12)');
const nativeMaterialTick = ref(0);
let floatGlassSyncTimer = null;
const popCardRef = ref(null);
const railRef = ref(null);
const itemRefs = ref({});
const popTailTop = ref(48);
const popOffsetY = ref(0);
let popupResizeObserver = null;
const cursorBusy = ref(false);
const codexBusy = ref(false);
let codexActivityTimer = null;
let activityDisposed = false;
const popTailStyle = computed(() => ({
  '--pop-tail-top': `${popTailTop.value}px`,
}));
let unsub = null;
let cursorActivityTimer = null;
let cursorBusyHoldMs = 0;
let cursorBusyStreak = 0;
let cursorIdleStreak = 0;
const drag = createRailDrag({
  start: () => seeUtoken.setFloatDragging(true).catch(() => {}),
  move: (dx, dy) => seeUtoken.moveFloatBy(dx, dy),
  end: () => seeUtoken.setFloatDragging(false).catch(() => {}),
});
let hoverHideTimer = null;

useLiquidGlass({
  popRef: popCardRef,
  railRef,
  glassStyle: floatGlassStyle,
  hoveredId,
  nativeMaterialTick,
});

useNativeGlassShape({
  railRef,
  popRef: popCardRef,
  hoveredId,
  popTailTop,
  popOffsetY,
  glassStyle: floatGlassStyle,
  nativeMaterialTick,
  dockState,
  tabRef: edgeTabRef,
});

const visibleServices = computed(() =>
  panelTypes.value.map((id) => PROVIDER_META[id]).filter(Boolean)
);

const primaryMeta = computed(() => visibleServices.value[0] || PROVIDER_META.cursor);

const hoveredMeta = computed(() => (hoveredId.value ? PROVIDER_META[hoveredId.value] : null));

const cursorPct = computed(() => {
  if (!usageData.value) return 0;
  const q = usageData.value.quota || {};
  const l = usageData.value.limits || {};
  return Math.round(
    Number(
      l.cursorModelsPercent ?? q.cursorModelsPercent ?? q.autoPercent ?? 0
    ) || 0
  );
});
function usedDonutSegments(usedPct, color) {
  const used = Math.min(100, Math.max(0, Number(usedPct) || 0));
  const remain = Math.max(0, 100 - used);
  const track = donutTrack.value;
  if (used + remain <= 0) return [{ value: 1, color: track }];
  // 灰色 = 已用，彩色 = 剩余（与首页额度卡片一致）
  return [
    { value: used || 0.0001, color: track },
    { value: remain || 0.0001, color },
  ];
}

const otherPct = computed(() =>
  Math.round(
    Number(
      usageData.value?.limits?.otherModelsPercent ?? usageData.value?.quota?.apiPercent ?? 0
    ) || 0
  )
);

const cursorRemainPct = computed(() => Math.max(0, 100 - cursorPct.value));
const otherRemainPct = computed(() => Math.max(0, 100 - otherPct.value));

const cursorDonutSegments = computed(() => usedDonutSegments(cursorPct.value, '#34d399'));
const otherDonutSegments = computed(() => usedDonutSegments(otherPct.value, '#a78bfa'));

function poolTodayTokens(pool) {
  const data = usageData.value;
  if (!data) return 0;
  const fromPool = data.todayPoolTokens?.[pool];
  if (fromPool && fromPool.tokens != null) {
    return Number(fromPool.tokens) || 0;
  }
  const list = data.models?.today;
  if (Array.isArray(list) && list.length) {
    let sum = 0;
    let seen = false;
    for (const m of list) {
      if (!m || typeof m !== 'object') continue;
      const key = m.pool === 'cursor' ? 'cursor' : 'other';
      if (key !== pool) continue;
      seen = true;
      const input = Number(m.input) || 0;
      const output = Number(m.output) || 0;
      sum += m.tokens != null ? Number(m.tokens) || 0 : input + output;
    }
    if (seen) return sum;
  }
  return 0;
}

const cursorTodayTokens = computed(() => poolTodayTokens('cursor'));
const otherTodayTokens = computed(() => poolTodayTokens('other'));

function periodTokenCount(data, periodKey) {
  if (!data || typeof data !== 'object') return null;
  const fromUsage = data.usageTokens?.[periodKey];
  if (fromUsage != null && Number.isFinite(Number(fromUsage))) {
    return Number(fromUsage);
  }
  const p = data.periods?.[periodKey];
  if (p && typeof p === 'object') {
    const total = Number(p.tokens ?? ((Number(p.input) || 0) + (Number(p.output) || 0)));
    const hasSignal =
      total > 0 ||
      Number(p.cost) > 0 ||
      p.calls != null ||
      Number(p.input) > 0 ||
      Number(p.output) > 0;
    if (hasSignal || !data.partial) return total;
  }
  const pools = data.todayPoolTokens;
  if (pools && periodKey === 'today') {
    const sum =
      (Number(pools.cursor?.tokens) || 0) + (Number(pools.other?.tokens) || 0);
    if (sum > 0 || !data.partial) return sum;
  }
  const list = data.models?.today;
  if (Array.isArray(list) && list.length && periodKey === 'today') {
    let sum = 0;
    let seen = false;
    for (const m of list) {
      if (!m || typeof m !== 'object') continue;
      const input = Number(m.input) || 0;
      const output = Number(m.output) || 0;
      const tokens = m.tokens != null ? Number(m.tokens) || 0 : input + output;
      sum += tokens;
      seen = true;
    }
    if (seen) return sum;
  }
  return null;
}

const todayTokenTotal = computed(() => {
  const fromPeriod = periodTokenCount(usageData.value, 'today');
  if (fromPeriod != null) return fromPeriod;
  return cursorTodayTokens.value + otherTodayTokens.value;
});

function mergeUsageData(next, prev) {
  const normalized = normalizeUsageData(next);
  if (!prev || typeof prev !== 'object') return normalized;
  if (!normalized || typeof normalized !== 'object') return prev;
  const merged = { ...normalized };
  const nextToday = periodTokenCount(merged, 'today');
  const prevToday = periodTokenCount(prev, 'today');
  const prevCycle = periodTokenCount(prev, 'cycle');
  const nextCycle = periodTokenCount(merged, 'cycle');
  if (nextToday == null && prevToday != null) {
    merged.usageTokens = {
      ...(merged.usageTokens || {}),
      today: prevToday,
      cycle: nextCycle ?? prevCycle ?? merged.usageTokens?.cycle,
    };
    if (!merged.periods && prev.periods) merged.periods = prev.periods;
    if (!merged.todayPoolTokens && prev.todayPoolTokens) {
      merged.todayPoolTokens = prev.todayPoolTokens;
    }
  }
  if (merged.partial && prevToday != null) {
    merged.usageTokens = {
      ...(merged.usageTokens || {}),
      today: merged.usageTokens?.today ?? prevToday,
      cycle: merged.usageTokens?.cycle ?? prevCycle,
    };
    if (!merged.todayPoolTokens && prev.todayPoolTokens) {
      merged.todayPoolTokens = prev.todayPoolTokens;
    }
  }
  return merged;
}

async function pullUsageTokens() {
  try {
    const res = await seeUtoken.getUsageTokens();
    if (!res?.ok || res.today == null) return;
    usageData.value = mergeUsageData(
      {
        ...(usageData.value || {}),
        usageTokens: { today: Number(res.today), cycle: Number(res.cycle ?? 0) },
        includeCachedTokens: res.includeCachedTokens,
        partial: !!res.partial,
      },
      usageData.value
    );
  } catch (_) {}
}

function normalizeUsageData(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  const next = { ...raw };
  if (!next.todayPoolTokens && Array.isArray(next.models?.today) && next.models.today.length) {
    const acc = {
      cursor: { tokens: 0, input: 0, output: 0 },
      other: { tokens: 0, input: 0, output: 0 },
    };
    for (const m of next.models.today) {
      if (!m || typeof m !== 'object') continue;
      const pool = m.pool === 'cursor' ? 'cursor' : 'other';
      const input = Number(m.input) || 0;
      const output = Number(m.output) || 0;
      const tokens = m.tokens != null ? Number(m.tokens) || 0 : input + output;
      acc[pool].input += input;
      acc[pool].output += output;
      acc[pool].tokens += tokens;
    }
    next.todayPoolTokens = acc;
  }
  const today = periodTokenCount(next, 'today');
  if (today != null) {
    next.usageTokens = { ...(next.usageTokens || {}), today };
  }
  return next;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pullCursorActivity() {
  try {
    const res = await seeUtoken.getCursorActivity();
    const busy = !!res?.busy;
    const now = Date.now();
    if (busy) {
      cursorBusyStreak += 1;
      cursorIdleStreak = 0;
      if (cursorBusyStreak >= 2) {
        cursorBusyHoldMs = now + 800;
        cursorBusy.value = true;
      }
      return;
    }
    cursorIdleStreak += 1;
    cursorBusyStreak = 0;
    if (cursorIdleStreak >= 2) {
      cursorBusy.value = now < cursorBusyHoldMs;
    }
  } catch (_) {}
}

async function pullCodexActivity() {
  try {
    const result = await seeUtoken.getCodexActivity();
    if (!activityDisposed) codexBusy.value = !!(result?.ok && result.busy);
  } catch (_) {
    codexBusy.value = false;
  } finally {
    if (!activityDisposed) codexActivityTimer = window.setTimeout(pullCodexActivity, 1500);
  }
}

const ballPercent = computed(() => {
  if (primaryMeta.value.id === 'cursor') return cursorPct.value;
  return 0;
});

const ballPercentLabel = computed(() => {
  if (primaryMeta.value.id === 'cursor' && usageData.value) return `${ballPercent.value}%`;
  return '0%';
});

const ballOffset = computed(() => BALL_C * (1 - Math.min(100, ballPercent.value) / 100));

const resetText = computed(() => {
  const ts = usageData.value?.cycle?.resetAt || usageData.value?.cycle?.end;
  if (!ts) return '—';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '—';
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')} 重置`;
});

function itemTitle(svc) {
  if (svc.id === 'cursor' || svc.id === 'codex') return `${svc.name} · 双击进入详情`;
  return svc.name;
}

function onItemDblClick(svc) {
  if (drag.moved) return;
  if (svc.id === 'cursor') openDetail();
  if (svc.id === 'codex') seeUtoken.openDashboardDetail('codex');
  if (!svc.live) seeUtoken.openDashboard();
}

function uniquePanelTypes(panels) {
  if (!Array.isArray(panels)) return [...DEFAULT_PANEL_TYPES];
  const seen = new Set();
  const out = [];
  for (const p of panels) {
    if (!p || typeof p !== 'object') continue;
    const t = p.type || p.provider || 'cursor';
    if (!PROVIDER_META[t] || seen.has(t)) continue;
    seen.add(t);
    out.push(t);
  }
  return out;
}

function percentFor(svc) {
  if (!svc.live) return 100;
  if (svc.id === 'codex') {
    const win = codexData.value?.windows?.[0];
    return win?.remainingPercent == null ? 100 : win.usedPercent;
  }
  if (svc.id === 'cursor' && usageData.value && !usageData.value.demo) return cursorPct.value;
  return 0;
}

function percentLabel(svc) {
  if (svc.id === 'codex') return quotaText(codexData.value?.windows?.[0]);
  if (svc.id === 'cursor' && usageData.value && !usageData.value.demo) {
    return `${cursorRemainPct.value}%`;
  }
  return '0%';
}

/** 外环：灰色底 = 已用，彩色弧 = 剩余（与弹窗圆环一致） */
function ringOffset(p) {
  const used = Math.max(0, Math.min(100, Number(p) || 0));
  return RING_C * (used / 100);
}

function clearHoverTimer() {
  if (hoverHideTimer) {
    window.clearTimeout(hoverHideTimer);
    hoverHideTimer = null;
  }
}

function setItemRef(id) {
  return (el) => {
    if (el) itemRefs.value[id] = el;
    else delete itemRefs.value[id];
  };
}

function updatePopTail() {
  const id = hoveredId.value;
  if (!id) return;
  const item = itemRefs.value[id];
  const pop = popCardRef.value;
  if (!item || !pop) return;
  const ringEl = item.querySelector?.('.ring') || item;
  const itemRect = ringEl.getBoundingClientRect();
  const popRect = pop.getBoundingClientRect();
  const centerY = itemRect.top + itemRect.height / 2;
  const placement = popupPlacement({
    centerY,
    popupHeight: popRect.height,
    baseTop: popRect.top - popOffsetY.value,
    viewportHeight: window.innerHeight,
    radius: parseFloat(getComputedStyle(pop).borderRadius) || 36,
  });
  popOffsetY.value = placement.offsetY;
  popTailTop.value = placement.tailTop;
}

function onItemEnter(id) {
  if (dockState.value.collapsed) return;
  clearHoverTimer();
  if (hoveredId.value !== id) {
    seeUtoken.performHaptic('max');
  }
  hoveredId.value = id;
  nextTick(updatePopTail);
}

watch([hoveredId, panelTypes, floatGlassStyle], () => {
  nextTick(updatePopTail);
});

watch(popCardRef, (pop) => {
  popupResizeObserver?.disconnect();
  if (pop) {
    popupResizeObserver = new ResizeObserver(updatePopTail);
    popupResizeObserver.observe(pop);
  }
});

function onDockLeave() {
  clearHoverTimer();
  hoverHideTimer = window.setTimeout(() => {
    hoveredId.value = null;
    hoverHideTimer = null;
  }, 220);
}

// AppKit delivers these coordinates even while a different app has focus.
// Reuse the DOM handlers so native and browser hover keep the same behavior.
function onNativePointer(point) {
  if (dockState.value.collapsed) return;
  if (drag.active) return;
  const target = point ? document.elementFromPoint(point.x, point.y) : null;
  const item = target?.closest('.item[data-provider-id]');
  if (item) {
    onItemEnter(item.dataset.providerId);
  } else if (target?.closest('.dock')) {
    clearHoverTimer();
  } else if (hoveredId.value && !hoverHideTimer) {
    onDockLeave();
  }
}

function applyFloatGlassFromSettings(settings) {
  const nextIncludeCache = !!settings?.includeCachedTokens;
  if (nextIncludeCache !== includeCachedTokens) {
    includeCachedTokens = nextIncludeCache;
    pullUsageTokens();
    refreshCodex();
  }
  floatGlassStyle.value = normalizeFloatGlassStyle(settings?.floatGlassStyle);
  if (Array.isArray(settings?.panels)) {
    panelTypes.value = uniquePanelTypes(settings.panels);
    if (hoveredId.value && !panelTypes.value.includes(hoveredId.value)) {
      clearHoverTimer();
      hoveredId.value = null;
    }
    nextTick(updatePopTail);
  }
}

async function syncFloatGlassStyle() {
  try {
    const settings = await seeUtoken.getSettings();
    applyFloatGlassFromSettings(settings);
  } catch (_) {}
}

async function syncNativeMaterialFromApi() {
  try {
    const state = await seeUtoken.getNativeMaterialState();
    if (typeof window.__seeUtokenApplyNativeMaterial === 'function') {
      window.__seeUtokenApplyNativeMaterial(state);
    }
  } catch (_) {}
}

async function setExpanded(next) {
  expanded.value = next;
  if (!next) hoveredId.value = null;
  await seeUtoken.setFloatExpanded(next);
}

function onDragStart(e) {
  drag.down(e);
}
function onDragMove(e) {
  drag.move(e);
}
function onDragEnd(e) {
  drag.up(e);
}

function openDetail() {
  seeUtoken.openDashboardDetail();
}
async function refresh() {
  refreshing.value = true;
  const prev = usageData.value;
  try {
    await seeUtoken.refreshUsage();
    await pullUsageTokens();
    for (let i = 0; i < 20; i += 1) {
      await sleep(300);
      const pushed = seeUtoken.takeLastCard?.();
      if (pushed?.data) {
        usageData.value = mergeUsageData(pushed.data, usageData.value);
        if (periodTokenCount(usageData.value, 'today') != null && !usageData.value?.partial) {
          break;
        }
      }
      try {
        const res = await seeUtoken.getUsageSummary();
        if (res?.data) {
          usageData.value = mergeUsageData(res.data, usageData.value);
          if (periodTokenCount(usageData.value, 'today') != null && !res.data?.partial) {
            break;
          }
        }
      } catch (_) {}
      await pullUsageTokens();
    }
    usageData.value = mergeUsageData(usageData.value, prev);
    await pullUsageTokens();
  } finally {
    refreshing.value = false;
  }
}

onMounted(async () => {
  window.addEventListener('resize', updatePopTail);
  window.__seeUtokenApplyFloatSettings = applyFloatGlassFromSettings;
  if (window.__seeUtokenFloatSettings) applyFloatGlassFromSettings(window.__seeUtokenFloatSettings);
  window.__seeUtokenApplyFloatDock = applyDockState;
  if (window.__seeUtokenFloatDock) applyDockState(window.__seeUtokenFloatDock);
  pullCodexActivity();
  window.__seeUtokenFloatPointer = onNativePointer;
  document.documentElement.style.background = 'transparent';
  document.body.style.background = 'transparent';
  installNativeMaterialHook((state) => {
    if (state.floatStyle) floatGlassStyle.value = normalizeFloatGlassStyle(state.floatStyle);
    nativeMaterialTick.value += 1;
  });
  unsub = seeUtoken.onUsageUpdated((payload) => {
    if (payload?.data) {
      usageData.value = mergeUsageData(payload.data, usageData.value);
    }
  });
  const primed = seeUtoken.takeLastCard?.();
  if (primed?.data) usageData.value = mergeUsageData(primed.data, usageData.value);
  const primedDetail = seeUtoken.takeLastDetail?.();
  if (primedDetail?.data) {
    usageData.value = mergeUsageData(primedDetail.data, usageData.value);
  }
  try {
    const settings = await seeUtoken.getSettings();
    applyFloatGlassFromSettings(settings);
    expanded.value = true;
    if (settings?.floatCollapsed !== false) {
      await seeUtoken.setFloatExpanded(true);
    }
  } catch (_) {}
  try {
    const res = await seeUtoken.getUsageSummary();
    if (res?.data) usageData.value = mergeUsageData(res.data, usageData.value);
  } catch (_) {}
  await pullUsageTokens();
  window.setInterval(() => {
    pullUsageTokens();
  }, 8000);
  await pullCursorActivity();
  cursorActivityTimer = window.setInterval(pullCursorActivity, 1500);
  floatGlassSyncTimer = window.setInterval(() => {
    syncFloatGlassStyle();
    syncNativeMaterialFromApi();
  }, 3000);
});

onUnmounted(() => {
  window.removeEventListener('resize', updatePopTail);
  popupResizeObserver?.disconnect();
  if (window.__seeUtokenApplyFloatSettings === applyFloatGlassFromSettings) delete window.__seeUtokenApplyFloatSettings;
  if (window.__seeUtokenApplyFloatDock === applyDockState) delete window.__seeUtokenApplyFloatDock;
  activityDisposed = true;
  if (codexActivityTimer) window.clearTimeout(codexActivityTimer);
  if (window.__seeUtokenFloatPointer === onNativePointer) {
    delete window.__seeUtokenFloatPointer;
  }
  if (unsub) unsub();
  if (hoverHideTimer) window.clearTimeout(hoverHideTimer);
  if (cursorActivityTimer) window.clearInterval(cursorActivityTimer);
  if (floatGlassSyncTimer) window.clearInterval(floatGlassSyncTimer);
});
</script>

<style>
html,
body,
#app {
  margin: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: transparent !important;
}
</style>

<style scoped>
.root {
  width: 100%;
  height: 100%;
  position: relative;
  user-select: none;
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: transparent;
  overflow: visible;
}

.ball {
  position: absolute;
  inset: 4px;
  border: 0;
  padding: 0;
  border-radius: 50%;
  background: transparent;
  cursor: grab;
}
.ball:active {
  cursor: grabbing;
}
.ball-ring {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}
.ball-ring .track {
  fill: none;
  stroke: rgba(255, 255, 255, 0.18);
  stroke-width: 4;
}
.ball-ring .value {
  fill: none;
  stroke-width: 4;
  stroke-linecap: round;
  transition: stroke-dashoffset 0.4s ease;
}
.ball-core {
  position: absolute;
  inset: 8px;
  border-radius: 50%;
  background: #121218;
  border: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  color: #fff;
  overflow: hidden;
}
.ball-logo {
  width: 18px;
  height: 18px;
  display: block;
  object-fit: contain;
  border-radius: 4px;
}
.ball-core b {
  font-size: 9px;
  font-variant-numeric: tabular-nums;
}

.panel {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: flex-end;
  padding: 18px 0;
  background: transparent;
  overflow: visible;
  pointer-events: none;
}

.edge-tab {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  padding: 0;
  border: 0;
  border-radius: 3px;
  background: #363d47;
  box-shadow: none;
  cursor: pointer;
}
.edge-left .panel { justify-content: flex-start; }
.edge-left .dock { flex-direction: row-reverse; }
.edge-left .rail { margin-left: 0; margin-right: 14px; }
.edge-left .pop-anchor { flex-direction: row-reverse; }
.edge-left .pop-tail { transform: scaleX(-1); }

.dock {
  position: relative;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: flex-end;
  height: 100%;
  pointer-events: auto;
}

.pop-anchor {
  position: relative;
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  flex-shrink: 0;
  width: auto;
  overflow: visible;
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
}

.pop-anchor.visible {
  opacity: 1;
  visibility: visible;
  pointer-events: auto;
}

.rail {
  position: relative;
  flex-shrink: 0;
  width: 66px;
  height: fit-content;
  border-radius: 999px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 14px 10px;
  cursor: grab;
  box-sizing: border-box;
  margin-left: 14px;
}

.item {
  border: 0;
  background: transparent;
  color: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  cursor: pointer;
  position: relative;
  font: inherit;
  padding: 0;
  outline: none;
  box-shadow: none;
  -webkit-appearance: none;
  appearance: none;
}
.item:focus,
.item:focus-visible {
  outline: none;
  box-shadow: none;
}
.ring {
  width: 40px;
  height: 40px;
  position: relative;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.06);
  box-shadow:
    inset 0 0 0 0.5px rgba(232, 238, 244, 0.14),
    var(--liquid-glass-specular, inset 0 1px 0 rgba(255, 255, 255, 0.1));
  -webkit-backdrop-filter: blur(10px) saturate(160%);
  backdrop-filter: blur(10px) saturate(160%);
}
.ring svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}
.ring-track {
  fill: none;
  stroke: rgba(255, 255, 255, 0.2);
  stroke-width: 2.5;
}
.ring-value {
  fill: none;
  stroke-width: 2.5;
  stroke-linecap: round;
}
.icon {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: grid;
  place-items: center;
  position: relative;
  z-index: 1;
  overflow: hidden;
}
.icon.cursor,
.icon.codex,
.icon.qoder {
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
  overflow: visible;
}
.ring.provider-busy::after {
  content: '';
  position: absolute;
  /* 贴合外环内缘：viewBox 38，半径 17，描边宽 2.5。 */
  inset: 8.552632%;
  border-radius: 50%;
  border: 2px solid transparent;
  border-top-color: #fff;
  border-right-color: #fff;
  box-shadow: none;
  animation: provider-busy-spin 1.2s linear infinite;
  pointer-events: none;
  z-index: 2;
}
@keyframes provider-busy-spin {
  to {
    transform: rotate(360deg);
  }
}
.icon-img {
  width: 22px;
  height: 22px;
  display: block;
  object-fit: contain;
}
.icon.codex .icon-img,
.icon.qoder .icon-img {
  filter: brightness(0) invert(1);
}
.pct {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.75);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.pct.muted {
  color: rgba(255, 255, 255, 0.35);
  font-weight: 500;
}
.pop {
  width: 300px;
  flex-shrink: 0;
  padding: 18px 18px 16px;
  border-radius: 36px;
  color: #fff;
  box-sizing: border-box;
  position: relative;
}
/* 夹在大弹窗与侧边栏之间的指向三角（独立占位，不被 rail 遮挡） */
.pop-tail {
  flex-shrink: 0;
  width: 16px;
  height: 24px;
  margin-top: calc(var(--pop-tail-top, 48px) - 12px);
  position: relative;
  pointer-events: none;
}
.pop-tail::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  border-top: 12px solid transparent;
  border-bottom: 12px solid transparent;
  border-left: 14px solid var(--float-tail-stroke, rgba(255, 255, 255, 0.12));
}
.pop-tail::after {
  content: '';
  position: absolute;
  left: 1px;
  top: 1px;
  border-top: 11px solid transparent;
  border-bottom: 11px solid transparent;
  border-left: 13px solid var(--float-tail-fill, rgba(28, 28, 34, 0.52));
}
.pop-muted .pop-tail::after {
  border-left-color: var(--float-tail-fill, rgba(28, 28, 34, 0.52));
}
.pop-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}
.pop-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  min-width: 0;
}
.pop-plan {
  margin-left: auto;
  min-width: 0;
  max-width: 96px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgba(255, 255, 255, 0.9);
  font-size: 12px;
  font-weight: 500;
  text-transform: capitalize;
}
.pop-refresh {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0.5px solid rgba(232, 238, 244, 0.16);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  box-shadow: var(--liquid-glass-specular, inset 0 1px 0 rgba(255, 255, 255, 0.12));
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
  font-size: 14px;
  transition: background 0.15s ease, color 0.15s ease;
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
}
.pop-refresh:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
}
.pop-refresh:disabled {
  opacity: 0.55;
  cursor: default;
}
.pop-logo {
  width: 22px;
  height: 22px;
  display: block;
  object-fit: contain;
  border-radius: 6px;
}
.pop-logo.codex,
.pop-logo.qoder {
  filter: brightness(0) invert(1);
}
.pop-donuts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 12px;
  margin-bottom: 10px;
}
.pop-donut {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.donut-pct {
  color: #fff;
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
}
.donut-cap {
  margin-top: 2px;
  color: rgba(255, 255, 255, 0.62);
  font-size: 10px;
  font-weight: 600;
}
.pop-donut-name {
  color: rgba(255, 255, 255, 0.55);
  font-size: 11px;
  font-weight: 600;
  text-align: center;
  line-height: 1.3;
}
.pop-total-row {
  width: 100%;
  margin-bottom: 10px;
  padding: 10px 12px;
  text-align: center;
  border-radius: 20px;
  /* token-monitor --sunken-rgb：下沉表面比面板更深一档 */
  background: rgba(4, 8, 13, 0.32);
  border: 0.5px solid rgba(232, 238, 244, 0.1);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
  box-sizing: border-box;
}
.pop-donut-metrics {
  width: 100%;
  margin-top: 8px;
  padding: 0 2px;
  text-align: center;
}
.pop-total-label {
  color: rgba(255, 255, 255, 0.42);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.pop-total-value {
  display: block;
  margin-top: 6px;
  color: inherit;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.pop-total-value.bump {
  transform: scale(1.04);
}
.pop-reset {
  margin-bottom: 10px;
  color: rgba(255, 255, 255, 0.45);
  font-size: 11px;
  text-align: center;
}
.codex-resets {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 0;
  padding: 0 3px;
}
.codex-reset-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  line-height: 1.5;
}
.codex-reset-time {
  color: rgba(255, 255, 255, 0.65);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.pop-muted .pop-status {
  margin: 12px 0 8px;
  font-size: 18px;
  font-weight: 700;
  color: #fff;
}
.pop-muted .pop-desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.5);
}
</style>
