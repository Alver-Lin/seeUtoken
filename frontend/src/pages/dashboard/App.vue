<template>
  <div class="quota-page">
    <div class="toolbar dashboard-toolbar">
      <div class="toolbar-main">
        <a-button type="text" class="back-btn" @click="goPanels">
          <template #icon><ArrowLeftOutlined /></template>
        </a-button>
        <div class="toolbar-heading">
          <img class="toolbar-brand" :src="cursorLogo" alt="" />
          <div class="toolbar-title">Cursor</div>
          <button
            v-if="needsLogin"
            type="button"
            class="toolbar-account toolbar-account-btn"
            @click="startLogin"
          >
            未登录 · 点击登录
          </button>
          <span v-else-if="!data?.user?.email" class="toolbar-account">同步登录中…</span>
          <span v-else class="toolbar-account">{{ maskEmail(data?.user?.email) }}</span>
        </div>
      </div>
      <div class="toolbar-actions">
        <span v-if="lastUpdatedLabel" class="toolbar-updated">{{ lastUpdatedLabel }}</span>
        <a-button
          v-if="needsLogin"
          type="primary"
          :loading="loggingIn"
          @click="startLogin"
        >
          登录 Cursor
        </a-button>
        <div class="refresh-controls">
          <a-select
            v-model:value="autoRefreshMinutes"
            class="refresh-interval"
            size="middle"
            aria-label="Cursor 自动刷新间隔"
            @change="saveAutoRefresh"
          >
            <a-select-option :value="0">手动刷新</a-select-option>
            <a-select-option :value="1">每 1 分钟</a-select-option>
            <a-select-option :value="5">每 5 分钟</a-select-option>
            <a-select-option :value="15">每 15 分钟</a-select-option>
            <a-select-option :value="30">每 30 分钟</a-select-option>
          </a-select>
          <a-button class="refresh-now" :type="needsLogin ? 'default' : 'primary'" :loading="refreshing" @click="refresh">
            <template #icon><ReloadOutlined /></template>
            立即刷新
          </a-button>
        </div>
      </div>
    </div>

    <section class="mid">
      <article class="panel">
        <header class="panel-head">
          <div>
            <h3 class="panel-title">账户额度</h3>
            <p class="panel-sub">{{ cycleLabel }}</p>
          </div>
          <span v-if="data?.user?.membership" class="quota-plan">{{ data.user.membership }}</span>
        </header>
        <div class="pool-donuts">
          <div class="pool-donut">
            <DonutChart :size="168" :cutout="0.72" :segments="cursorPoolSegments" track="#e6ebf2">
              <template #center>
                <div class="donut-value sm">{{ formatPercent(cursorRemainPct) }}</div>
                <div class="donut-label">剩余</div>
              </template>
            </DonutChart>
            <div class="pool-donut-title">Cursor 模型</div>
          </div>
          <div class="pool-donut">
            <DonutChart :size="168" :cutout="0.72" :segments="otherPoolSegments" track="#e6ebf2">
              <template #center>
                <div class="donut-value sm">{{ formatPercent(otherRemainPct) }}</div>
                <div class="donut-label">剩余</div>
              </template>
            </DonutChart>
            <div class="pool-donut-title">其余模型</div>
          </div>
        </div>
        <div class="reset-block">
          <div>
            <div class="reset-k">到期重置</div>
            <div class="reset-when">{{ formatDateTime(resetAt) }}</div>
          </div>
          <div class="reset-left">{{ formatCountdown(resetAt) }}</div>
        </div>
      </article>

      <article class="panel">
        <header class="panel-head">
          <div>
            <h3 class="panel-title">模型 Token 用量</h3>
          </div>
          <div class="model-filters">
            <a-radio-group v-model:value="poolFilter" size="small" button-style="solid">
              <a-radio-button value="all">全部</a-radio-button>
              <a-radio-button value="cursor">Cursor</a-radio-button>
              <a-radio-button value="other">其余</a-radio-button>
            </a-radio-group>
            <a-radio-group v-model:value="period" size="small" button-style="solid">
              <a-radio-button value="today">今日</a-radio-button>
              <a-radio-button value="week">本周</a-radio-button>
              <a-radio-button value="month">本月</a-radio-button>
              <a-radio-button value="cycle">本周期</a-radio-button>
              <a-radio-button value="all">全部</a-radio-button>
            </a-radio-group>
          </div>
        </header>

        <div v-if="filteredModels.length" class="model-body">
          <div class="model-pie-box" :title="periodTokensExactTitle">
            <DonutChart :size="200" :cutout="0.7" :segments="modelSegments" track="#e6ebf2">
              <template #center>
                <div class="model-pie-value">{{ formatTokens(periodTokens) }}</div>
                <div class="model-pie-label">Token 合计</div>
              </template>
            </DonutChart>
          </div>
          <div class="model-list">
            <div
              v-for="(m, i) in filteredModels"
              :key="m.model"
              class="model-row"
              :title="modelTokenExactTitle(m)"
            >
              <div class="model-top">
                <i class="swatch" :style="{ background: colors[i % colors.length] }" />
                <span class="model-name" :title="m.model">{{ m.model }}</span>
                <span class="model-amt">{{ formatTokens(m.tokens ?? modelTokens(m)) }}</span>
                <span class="model-pct">{{ pct(m.percent) }}%</span>
              </div>
              <div class="model-bar">
                <span
                  :style="{
                    width: `${Math.max(m.percent, 1.5)}%`,
                    background: colors[i % colors.length],
                  }"
                />
              </div>
              <div class="model-meta">
                <template v-if="m.calls != null">{{ m.calls }} 次 · </template>
                输入 {{ formatTokens(m.input) }} · 输出 {{ formatTokens(m.output) }} · 缓存
                {{ formatTokens(m.cache) }}
                <template v-if="m.pool"> · {{ m.pool === 'cursor' ? 'Cursor' : '其余' }}</template>
              </div>
            </div>
          </div>
        </div>
        <p v-else class="block-empty">该时段暂无模型 Token 用量</p>
      </article>
    </section>

    <section class="panel usage-records">
      <header class="panel-head">
        <div>
          <h3 class="panel-title">使用记录</h3>
        </div>
      </header>
      <div class="table-wrap">
        <a-table
          size="small"
          table-layout="fixed"
          :columns="columns"
          :data-source="records"
          :pagination="{ pageSize: 8, showSizeChanger: false, hideOnSinglePage: true }"
          row-key="time"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'prompt'">
              <span class="question-content" :title="record.prompt || undefined">{{ record.prompt || '—' }}</span>
            </template>
            <template v-if="column.key === 'token'">
              <div class="token-cell">
                <span class="token-part"
                  ><em>输入</em> {{ formatTokens(record.input) }}</span
                >
                <span class="token-part"
                  ><em>输出</em> {{ formatTokens(record.output) }}</span
                >
                <span class="token-part"
                  ><em>缓存</em> {{ formatTokens(record.cache) }}</span
                >
              </div>
            </template>
          </template>
        </a-table>
      </div>
    </section>

    <HeatmapBoard v-model="heatmap" />
    <UsageTrendBoard :heatmap="heatmap" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { message } from 'ant-design-vue';
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons-vue';
import { seeUtoken } from '../../bridge';
import { tokenBasisLabel } from '../../utils/tokenAccounting';
import DonutChart from '../../components/DonutChart.vue';
import HeatmapBoard from '../../components/HeatmapBoard.vue';
import UsageTrendBoard from '../../components/UsageTrendBoard.vue';
import cursorLogo from '../../assets/brand/cursor-logo.svg';
import {
  formatCountdown,
  formatDateRange,
  formatDateTime,
  formatPercent,
  formatTokens,
  formatTokensExact,
  kindLabel,
  maskEmail,
} from '../../utils/format';

const colors = ['#1677ff', '#69b1ff', '#91caff', '#bae0ff', '#003eb3', '#4096ff', '#597ef7'];

const data = ref(null);
const period = ref('cycle');
const poolFilter = ref('all');
const refreshing = ref(false);
const loggingIn = ref(false);
const lastUpdatedAt = ref(null);

const lastUpdatedLabel = computed(() => {
  if (!lastUpdatedAt.value) return '';
  const t = new Date(lastUpdatedAt.value).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
  return `更新时间 ${t}`;
});

function markUpdated(ts) {
  lastUpdatedAt.value = ts || Date.now();
}
const heatmap = ref(null);
const hasSessionHint = ref(false);
const authRequired = ref(false);
const autoRefreshMinutes = ref(5);
let unsub = null;
let unsubHeatmap = null;
let refreshWatchdog = null;

const needsLogin = computed(() => {
  if (authRequired.value) return true;
  const d = data.value;
  if (d?.demo) return true;
  if (d?.user?.email) return false;
  if (hasSessionHint.value) return false;
  return true;
});

function modelsHasData(models) {
  if (!models || typeof models !== 'object') return false;
  return Object.values(models).some((list) => Array.isArray(list) && list.length > 0);
}

function periodsHasData(periods) {
  if (!periods || typeof periods !== 'object') return false;
  return Object.values(periods).some(
    (p) => p && (Number(p.cost) > 0 || Number(p.input) > 0 || Number(p.output) > 0)
  );
}

const quota = computed(
  () =>
    data.value?.quota || {
      remaining: 0,
      total: 0,
      used: 0,
      usedPercent: 0,
      remainingPercent: 0,
      autoPercent: 0,
      apiPercent: 0,
      gifted: 0,
    }
);

function poolColor(usedPct) {
  const remain = Math.max(0, 100 - (Number(usedPct) || 0));
  const ratio = remain / 100;
  if (ratio <= 0) return '#ff4d4f';
  if (ratio < 0.2) return '#fa8c16';
  return '#1677ff';
}

function poolSegments(usedPct, color) {
  const used = Math.min(100, Math.max(0, Number(usedPct) || 0));
  const remain = Math.max(0, 100 - used);
  if (used + remain <= 0) return [{ value: 1, color: 'transparent' }];
  return [
    { value: remain || 0.0001, color },
    { value: used || 0.0001, color: 'transparent' },
  ];
}

function modelTokens(m) {
  if (m?.tokens != null) return Number(m.tokens) || 0;
  return (Number(m?.input) || 0) + (Number(m?.output) || 0);
}

const cycleLabel = computed(() => {
  const c = data.value?.cycle;
  if (!c?.start && !c?.end) return '计费周期未知';
  return formatDateRange(c.start, c.end) || '计费周期未知';
});

const resetAt = computed(() => data.value?.cycle?.resetAt || data.value?.cycle?.end || null);

const cursorUsedPct = computed(
  () => Number(quota.value.cursorModelsPercent ?? quota.value.autoPercent) || 0
);
const otherUsedPct = computed(
  () => Number(quota.value.otherModelsPercent ?? quota.value.apiPercent) || 0
);
const cursorRemainPct = computed(() => Math.max(0, 100 - cursorUsedPct.value));
const otherRemainPct = computed(() => Math.max(0, 100 - otherUsedPct.value));

const cursorPoolSegments = computed(() =>
  poolSegments(cursorUsedPct.value, poolColor(cursorUsedPct.value))
);
const otherPoolSegments = computed(() =>
  poolSegments(otherUsedPct.value, poolColor(otherUsedPct.value) === '#1677ff' ? '#13c2c2' : poolColor(otherUsedPct.value))
);

const models = computed(() => data.value?.models?.[period.value] || []);

const filteredModels = computed(() => {
  const list = models.value.map((m) => {
    const tokens = modelTokens(m);
    return { ...m, tokens };
  });
  const scoped =
    poolFilter.value === 'all' ? list : list.filter((m) => (m.pool || 'other') === poolFilter.value);
  const total = scoped.reduce((s, m) => s + m.tokens, 0) || 1;
  return scoped
    .map((m) => ({ ...m, percent: (m.tokens / total) * 100 }))
    .sort((a, b) => b.tokens - a.tokens);
});

const periodTokens = computed(() =>
  filteredModels.value.reduce((s, m) => s + (Number(m.tokens) || 0), 0)
);

const periodTokensExactTitle = computed(() => {
  const n = periodTokens.value;
  if (!n) return '';
  return `Token 合计：${formatTokensExact(n)}（${tokenBasisLabel(data.value?.includeCachedTokens)}）`;
});

function modelTokenExactTitle(m) {
  const total = modelTokens(m);
  const parts = [
    `合计 ${formatTokensExact(total)} Token`,
    `输入 ${formatTokensExact(m.input)}`,
    `输出 ${formatTokensExact(m.output)}`,
    `缓存 ${formatTokensExact(m.cache)}`,
  ];
  return parts.join(' · ');
}

const modelSegments = computed(() =>
  filteredModels.value.length
    ? filteredModels.value.map((m, i) => ({
        value: Math.max(m.tokens || 0, 0.0001),
        color: colors[i % colors.length],
      }))
    : [{ value: 1, color: 'transparent' }]
);

const columns = [
  { title: '时间', dataIndex: 'timeText', key: 'time', width: 164, ellipsis: true },
  { title: '模型', dataIndex: 'model', key: 'model', width: 132, ellipsis: true },
  { title: '使用项目', dataIndex: 'projectText', key: 'project', width: 100, ellipsis: true },
  { title: '会话内容', dataIndex: 'prompt', key: 'prompt', width: 172, ellipsis: true },
  {
    title: '类型',
    dataIndex: 'kindText',
    key: 'kind',
    width: 68,
    align: 'center',
    className: 'col-kind',
  },
  {
    title: 'Token',
    dataIndex: 'tokenText',
    key: 'token',
    className: 'col-token',
  },
];

const records = computed(() =>
  (data.value?.events || []).map((e) => ({
    ...e,
    timeText: formatDateTime(e.time),
    kindText: kindLabel(e.kind),
    projectText: e.project || '—',
    tokenText: `输入 ${formatTokens(e.input)} · 输出 ${formatTokens(e.output)} · 缓存 ${formatTokens(e.cache)}`,
  }))
);

function pct(p) {
  const n = Number(p) || 0;
  return n < 1 ? n.toFixed(1) : Math.round(n);
}

function isCardOnly(payload, incoming) {
  if (payload?.kind === 'card') return true;
  if (payload?.kind === 'detail' || payload?.kind === 'ack') return payload?.kind === 'ack' ? null : false;
  // 无 models/events 的精简包视为 card，避免把详情页清空
  return !!(
    incoming &&
    incoming.quota &&
    !modelsHasData(incoming.models) &&
    !(incoming.events || []).length
  );
}

function applyPayload(res) {
  if (!res || res.kind === 'ack') return;

  if (res.error?.code === 'NO_SESSION' || res.error?.code === 'AUTH_EXPIRED') {
    authRequired.value = true;
    hasSessionHint.value = false;
  } else if (!res.error && res.data?.user?.email && !res.data.demo) {
    authRequired.value = false;
  }

  if (res?.data) {
    const incoming = res.data;
    const cardOnly = isCardOnly(res, incoming);

    // 已有真实数据时，不要被演示数据盖掉
    if (incoming.demo && data.value && !data.value.demo) {
      refreshing.value = false;
      return;
    }

    // card 摘要：只合并额度/用户，绝不清空模型与使用记录
    if (cardOnly) {
      if (!data.value) {
        data.value = { ...incoming };
      } else {
        data.value = {
          ...data.value,
          demo: incoming.demo,
          partial: incoming.partial ?? data.value.partial,
          fetchedAt: incoming.fetchedAt || data.value.fetchedAt,
          authSource: incoming.authSource || data.value.authSource,
          user: incoming.user || data.value.user,
          cycle:
            incoming.cycle?.end || incoming.cycle?.start || incoming.cycle?.resetAt
              ? {
                  ...(data.value.cycle || {}),
                  ...incoming.cycle,
                  resetAt:
                    incoming.cycle?.resetAt ||
                    incoming.cycle?.end ||
                    data.value.cycle?.resetAt ||
                    data.value.cycle?.end,
                }
              : data.value.cycle,
          quota: incoming.quota || data.value.quota,
          limits: incoming.limits || data.value.limits,
        };
      }
      if (incoming.user?.email && !incoming.demo) hasSessionHint.value = true;
      if (modelsHasData(data.value?.models)) {
        markUpdated(res.updatedAt);
        refreshing.value = false;
      }
      return;
    }

    // partial / 空明细：保留旧的模型与使用记录，避免刷新时页面被清空
    if (data.value && !data.value.demo && !incoming.demo) {
      const keepModels = !modelsHasData(incoming.models) && modelsHasData(data.value.models);
      const keepEvents = !(incoming.events || []).length && (data.value.events || []).length;
      const keepPeriods = !periodsHasData(incoming.periods) && periodsHasData(data.value.periods);
      data.value = {
        ...data.value,
        ...incoming,
        models: keepModels ? data.value.models : incoming.models,
        events: keepEvents ? data.value.events : incoming.events,
        periods: keepPeriods ? data.value.periods : incoming.periods,
        heatmap: incoming.heatmap || data.value.heatmap,
      };
    } else {
      data.value = incoming;
    }

    if (incoming.user?.email && !incoming.demo) hasSessionHint.value = true;
    if (data.value?.heatmap) heatmap.value = data.value.heatmap;

    if (res.error) {
      if (res.error.code === 'NO_SESSION' || res.error.code === 'AUTH_EXPIRED') {
        hasSessionHint.value = false;
      }
      refreshing.value = false;
    } else if (incoming.demo) {
      refreshing.value = false;
    } else if (!incoming.partial) {
      markUpdated(res.updatedAt);
      refreshing.value = false;
    }
  } else if (res?.error) {
    refreshing.value = false;
  }
}

async function loadHeatmapIfNeeded() {
  if (heatmap.value?.months?.length) return;
  if (window.__seeUtokenLastHeatmap?.heatmap?.months?.length) {
    heatmap.value = window.__seeUtokenLastHeatmap.heatmap;
    return;
  }
  try {
    const year = new Date().getFullYear();
    // 后端不再经 API 回传大 JSON，改走 __seeUtokenHeatmapPush
    await seeUtoken.getHeatmap(year);
    for (let i = 0; i < 20; i++) {
      const pushed = window.__seeUtokenLastHeatmap;
      if (pushed?.heatmap?.months?.length) {
        heatmap.value = pushed.heatmap;
        return;
      }
      await new Promise((r) => setTimeout(r, 250));
    }
  } catch (_) {}
}

async function refresh() {
  refreshing.value = true;
  if (refreshWatchdog) window.clearTimeout(refreshWatchdog);
  refreshWatchdog = window.setTimeout(() => {
    refreshing.value = false;
  }, 20000);
  try {
    // 触发后台刷新；明细靠推送 / 轮询 getUsageDetail
    await seeUtoken.refreshUsage();
    for (let i = 0; i < 12; i++) {
      const detail =
        seeUtoken.takeLastDetail?.() ||
        (await seeUtoken.getUsageDetail().catch(() => null)) ||
        (await seeUtoken.getUsage(false).catch(() => null));
      if (detail?.data) applyPayload(detail);
      if (modelsHasData(data.value?.models) || (data.value?.events || []).length) {
        loadHeatmapIfNeeded();
        break;
      }
      await sleep(400);
    }
    loadHeatmapIfNeeded();
  } catch (e) {
    message.error(e.message || '加载失败');
    refreshing.value = false;
  }
}

async function saveAutoRefresh(minutes) {
  const n = Number(minutes) || 0;
  autoRefreshMinutes.value = n;
  await seeUtoken.setSettings({ autoRefreshMinutes: n });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function startLogin() {
  loggingIn.value = true;
  try {
    // 1) 本机已登录 Cursor → 直接同步，不弹网页
    const hint = await seeUtoken.getAuthHint();
    if (hint?.hasSession) {
      hasSessionHint.value = true;
      await refresh();
      // 等后台推送一小会儿
      await sleep(2500);
      if (data.value?.user?.email && !data.value?.demo && !needsLogin.value) {
        message.success('已识别本机 Cursor 登录');
        return;
      }
    }

    // 2) 未登录 → 打开 Cursor 登录页
    const res = await seeUtoken.startLogin();
    if (!res?.ok) {
      message.error(res?.error || '无法打开登录窗口');
      return;
    }
    message.info(res.alreadyOpen ? '登录窗口已打开' : '请在弹出窗口中登录 Cursor，完成后会自动同步');

    const started = Date.now();
    while (Date.now() - started < 5 * 60 * 1000) {
      await sleep(1500);
      const st = await seeUtoken.getLoginStatus();
      if (st?.done) {
        await refresh();
        message.success('登录成功');
        return;
      }
      if (!st?.open) {
        await refresh();
        if (needsLogin.value) {
          message.warning('未完成网页登录，可再试一次');
        }
        return;
      }
    }
    message.warning('登录超时，请重试');
  } catch (e) {
    message.error(e?.message || '打开登录失败');
  } finally {
    loggingIn.value = false;
  }
}

function goPanels() {
  seeUtoken.openPanels();
}

onMounted(async () => {
  unsub = seeUtoken.onUsageUpdated((payload) => {
    applyPayload(payload);
    loadHeatmapIfNeeded();
  });
  unsubHeatmap = seeUtoken.onHeatmapUpdated((payload) => {
    if (payload?.heatmap?.months?.length) heatmap.value = payload.heatmap;
  });

  try {
    const s = await seeUtoken.getSettings();
    autoRefreshMinutes.value = Number(s?.autoRefreshMinutes ?? 5);
  } catch (_) {}

  try {
    const hint = await seeUtoken.getAuthHint();
    hasSessionHint.value = !!hint?.hasSession;
  } catch (_) {}

  // 1) HTML bootstrap / 已推送的详情（不依赖 API 回传）
  const bootDetail = seeUtoken.takeLastDetail?.();
  if (bootDetail?.data) applyPayload(bootDetail);
  if (window.__seeUtokenLastHeatmap?.heatmap?.months?.length) {
    heatmap.value = window.__seeUtokenLastHeatmap.heatmap;
  }

  // 2) 再尝试 API；失败也不清空 bootstrap
  try {
    const cached =
      (await seeUtoken.getUsageDetail().catch(() => null)) ||
      (await seeUtoken.getUsage(false).catch(() => null));
    if (cached?.data && !cached.data.demo) applyPayload(cached);
  } catch (_) {}

  loadHeatmapIfNeeded();

  // 进入详情页刷新一次
  if (hasSessionHint.value || (data.value && !data.value.demo)) {
    refresh();
  }
});

onUnmounted(() => {
  if (unsub) unsub();
  if (unsubHeatmap) unsubHeatmap();
  if (refreshWatchdog) window.clearTimeout(refreshWatchdog);
});
</script>

<style scoped>
.quota-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 100vh;
  padding: 20px 24px 40px;
  background: var(--sut-bg, #f5f7f9);
  box-sizing: border-box;
}

.toolbar,
.panel {
  background: var(--sut-surface, #fff);
  border: 1px solid var(--sut-border, #e7ebf0);
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
  flex-wrap: wrap;
}

.toolbar-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.back-btn {
  color: var(--sut-secondary, #64748b);
  flex-shrink: 0;
}

.toolbar-heading {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.toolbar-brand {
  width: 22px;
  height: 22px;
  display: block;
  border-radius: 6px;
  flex-shrink: 0;
}

.toolbar-title {
  font-size: 15px;
  font-weight: 650;
  color: var(--sut-text, #1f2937);
}

.toolbar-account {
  color: var(--sut-secondary, #64748b);
  font-size: 12px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  line-height: 1.4;
}

.toolbar-account-btn {
  margin: 0;
  padding: 2px 8px;
  border: 1px solid #91caff;
  border-radius: 999px;
  background: var(--sut-accent-soft, #e8f3ff);
  color: var(--sut-primary, #1677ff);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
}

.toolbar-account-btn:hover {
  background: #d6eaff;
  border-color: #69b1ff;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-left: auto;
}

.toolbar-updated {
  color: var(--sut-muted, #94a3b8);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  user-select: none;
}

.panel-sub,
.model-meta {
  margin: 4px 0 0;
  color: var(--sut-muted, #8b95a5);
  font-size: 12px;
  line-height: 1.5;
}

.mid {
  display: grid;
  grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
  gap: 16px;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 14px 18px 8px;
}

.panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  color: var(--sut-text, #1f2937);
}

.quota-plan {
  color: var(--sut-text, #1f2937);
  font-size: 12px;
  line-height: 22px;
  white-space: nowrap;
}

.pool-donuts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 4px 12px 0;
}

.pool-donut {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.donut-value {
  color: var(--sut-text, #0f172a);
  font-size: 26px;
  font-weight: 720;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.03em;
}

.donut-value.sm {
  font-size: 20px;
}

.donut-label {
  margin-top: 2px;
  color: var(--sut-muted, #94a3b8);
  font-size: 12px;
}

.pool-donut-title {
  margin-top: 6px;
  color: var(--sut-text, #0f172a);
  font-size: 13px;
  font-weight: 650;
}

.swatch {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 6px;
  border-radius: 99px;
  background: var(--sut-primary, #1677ff);
}

.model-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.reset-block {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 14px 18px 18px;
  padding: 12px 14px;
  border-radius: 12px;
  background: var(--sut-inset, #f8fafc);
}

.reset-k {
  color: var(--sut-muted, #94a3b8);
  font-size: 12px;
}

.reset-when {
  margin-top: 2px;
  color: var(--sut-text, #0f172a);
  font-size: 14px;
  font-weight: 650;
}

.reset-left {
  color: var(--sut-primary, #1677ff);
  font-size: 13px;
  font-weight: 650;
}

.model-body {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 8px 12px;
  padding: 0 12px 16px;
}

.model-pie-box {
  position: relative;
  height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.model-pie-value {
  color: var(--sut-text, #0f172a);
  font-size: 20px;
  font-weight: 720;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.03em;
  line-height: 1.15;
}

.model-pie-label {
  margin-top: 2px;
  color: var(--sut-muted, #94a3b8);
  font-size: 12px;
}

.model-list {
  max-height: 320px;
  overflow: auto;
  padding-right: 6px;
}

.model-row + .model-row {
  margin-top: 12px;
}

.model-top {
  display: grid;
  grid-template-columns: 14px minmax(0, 1fr) auto auto;
  gap: 6px;
  align-items: center;
}

.model-name {
  overflow: hidden;
  color: var(--sut-text, #1f2937);
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-amt,
.model-pct {
  font-variant-numeric: tabular-nums;
  font-size: 12px;
}

.model-amt {
  color: var(--sut-text, #0f172a);
  font-weight: 650;
}

.model-pct {
  color: var(--sut-muted, #94a3b8);
  min-width: 42px;
  text-align: right;
}

.model-bar {
  height: 6px;
  margin: 6px 0 4px 20px;
  border-radius: 99px;
  background: var(--sut-track, #f1f5f9);
  overflow: hidden;
}

.model-bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.model-meta {
  margin-left: 20px;
}

.block-empty {
  margin: 0;
  padding: 28px 18px 32px;
  color: var(--sut-muted, #94a3b8);
  text-align: center;
}

@media (max-width: 1100px) {
  .mid,
  .model-body,
  .pool-donuts {
    grid-template-columns: 1fr;
  }
}
</style>
