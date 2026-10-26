<template>
  <div class="quota-page">
    <div class="toolbar">
      <div class="toolbar-main">
        <a-button type="text" class="back-btn" @click="goPanels">
          <template #icon><ArrowLeftOutlined /></template>
        </a-button>
        <div class="toolbar-heading">
          <img class="toolbar-brand" :src="cursorLogo" alt="" />
          <div class="toolbar-title">Cursor</div>
          <span class="toolbar-account">{{ maskEmail(data?.user?.email) }}</span>
        </div>
      </div>
      <div class="toolbar-actions">
        <a-tag v-if="statusText" :color="statusColor">{{ statusText }}</a-tag>
        <a-button @click="toggleFloat">{{ floatLabel }}</a-button>
        <a-button @click="tokenOpen = true">设置 Token</a-button>
        <a-button :loading="refreshing" @click="refresh">
          <template #icon><ReloadOutlined /></template>
          立即刷新
        </a-button>
        <a-button type="primary" @click="hide">收起到托盘</a-button>
      </div>
    </div>

    <section class="kpis">
      <article v-for="item in kpis" :key="item.key" class="kpi" :class="item.tone">
        <div class="kpi-top">
          <div class="kpi-label">{{ item.label }}</div>
          <span class="kpi-icon"><component :is="item.icon" /></span>
        </div>
        <div class="kpi-value">{{ item.value }}</div>
        <div class="kpi-sub">{{ item.sub }}</div>
      </article>
    </section>

    <section class="mid">
      <article class="panel">
        <header class="panel-head">
          <div>
            <h3 class="panel-title">额度存量</h3>
            <p class="panel-sub">{{ cycleLabel }}</p>
          </div>
        </header>
        <div class="donut-box">
          <DonutChart :size="200" :cutout="0.72" :segments="quotaSegments" track="#e6ebf2">
            <template #center>
              <div class="donut-value">{{ formatMoney(quota.remaining) }}</div>
              <div class="donut-label">剩余额度</div>
            </template>
          </DonutChart>
        </div>
        <div class="donut-legend">
          <span>
            <i class="swatch" :style="{ background: donutColor }" />
            剩余 {{ formatPercent(quota.remainingPercent) }}
          </span>
          <span>
            <i class="swatch used" />
            已用 {{ formatPercent(quota.usedPercent) }}
          </span>
        </div>
        <div class="reset-block">
          <div>
            <div class="reset-k">到期重置</div>
            <div class="reset-when">{{ formatDateTime(data?.cycle?.resetAt) }}</div>
          </div>
          <div class="reset-left">{{ formatCountdown(data?.cycle?.resetAt) }}</div>
        </div>
      </article>

      <article class="panel">
        <header class="panel-head">
          <div>
            <h3 class="panel-title">模型使用情况</h3>
            <p class="panel-sub">{{ modelsExtra || '按模型看用量和占比' }}</p>
          </div>
          <a-radio-group v-model:value="period" size="small" button-style="solid">
            <a-radio-button value="today">今日</a-radio-button>
            <a-radio-button value="week">本周</a-radio-button>
            <a-radio-button value="month">本月</a-radio-button>
            <a-radio-button value="cycle">本周期</a-radio-button>
            <a-radio-button value="all">全部</a-radio-button>
          </a-radio-group>
        </header>

        <div v-if="models.length" class="model-body">
          <div class="model-pie-box">
            <DonutChart :size="200" :cutout="0.7" :segments="modelSegments" track="#e6ebf2">
              <template #center>
                <div class="model-pie-value">{{ formatMoney(periodCost) }}</div>
                <div class="model-pie-label">使用金额</div>
              </template>
            </DonutChart>
          </div>
          <div class="model-list">
            <div v-for="(m, i) in models" :key="m.model" class="model-row">
              <div class="model-top">
                <i class="swatch" :style="{ background: colors[i % colors.length] }" />
                <span class="model-name" :title="m.model">{{ m.model }}</span>
                <span class="model-amt">{{ formatMoney(m.cost) }}</span>
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
                {{ m.calls }} 次 · Input {{ formatTokens(m.input) }} · Output
                {{ formatTokens(m.output) }} · Cache {{ formatTokens(m.cache) }}
              </div>
            </div>
          </div>
        </div>
        <p v-else class="block-empty">该时段暂无模型用量</p>
      </article>
    </section>

    <section class="panel">
      <header class="panel-head">
        <div>
          <h3 class="panel-title">使用记录</h3>
          <p class="panel-sub">按时间倒序，含模型和本次消耗</p>
        </div>
      </header>
      <div class="table-wrap">
        <a-table
          size="small"
          :columns="columns"
          :data-source="records"
          :pagination="{ pageSize: 8, showSizeChanger: false, hideOnSinglePage: true }"
          row-key="time"
        />
      </div>
    </section>

    <HeatmapBoard v-model="heatmap" />

    <a-modal v-model:open="tokenOpen" title="设置 Session Token" ok-text="保存并刷新" @ok="saveToken">
      <p class="panel-sub" style="margin-bottom: 12px">
        默认自动读取本机 Cursor 登录态。若失效，可粘贴浏览器 cursor.com 的
        <code>WorkosCursorSessionToken</code>。
      </p>
      <a-textarea v-model:value="tokenInput" :rows="4" placeholder="粘贴 token 或 sub::jwt …" />
      <template #footer>
        <a-button @click="tokenOpen = false">取消</a-button>
        <a-button @click="clearToken">清除</a-button>
        <a-button type="primary" @click="saveToken">保存并刷新</a-button>
      </template>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { message } from 'ant-design-vue';
import {
  ArrowLeftOutlined,
  ReloadOutlined,
  WalletOutlined,
  FireOutlined,
  CalendarOutlined,
  BarChartOutlined,
} from '@ant-design/icons-vue';
import { seeUtoken } from '../../bridge';
import DonutChart from '../../components/DonutChart.vue';
import HeatmapBoard from '../../components/HeatmapBoard.vue';
import cursorLogo from '../../assets/brand/cursor-logo.svg';
import {
  formatCountdown,
  formatDateRange,
  formatDateTime,
  formatMoney,
  formatPercent,
  formatTokens,
  kindLabel,
  maskEmail,
  startOfWeek,
} from '../../utils/format';

const colors = ['#1677ff', '#69b1ff', '#91caff', '#bae0ff', '#003eb3', '#4096ff', '#597ef7'];

const data = ref(null);
const period = ref('cycle');
const refreshing = ref(false);
const statusText = ref('同步中…');
const statusColor = ref('processing');
const floatLabel = ref('隐藏悬浮球');
const tokenOpen = ref(false);
const tokenInput = ref('');
const heatmap = ref(null);
let unsub = null;

const quota = computed(
  () => data.value?.quota || { remaining: 0, total: 0, usedPercent: 0, remainingPercent: 0 }
);

const cycleLabel = computed(() => {
  const c = data.value?.cycle;
  if (!c?.start && !c?.end) return '计费周期未知';
  return formatDateRange(c.start, c.end) || '计费周期未知';
});

const models = computed(() => data.value?.models?.[period.value] || []);
const periodCost = computed(() => data.value?.periods?.[period.value]?.cost || 0);
const modelsExtra = computed(() => {
  const p = data.value?.periods?.[period.value];
  if (!p) return '';
  return `合计 ${formatMoney(p.cost)} · ${p.calls} 次`;
});

const remainRatio = computed(() => {
  const r = Number(quota.value.remainingPercent) || 0;
  const u = Number(quota.value.usedPercent) || 0;
  const t = r + u;
  return t > 0 ? r / t : null;
});

const donutColor = computed(() => {
  const ratio = remainRatio.value;
  if (ratio == null) return '#d9e2ec';
  if (ratio <= 0) return '#ff4d4f';
  if (ratio < 0.2) return '#fa8c16';
  return '#1677ff';
});

const quotaSegments = computed(() => {
  const remain = Math.max(Number(quota.value.remaining) || 0, 0);
  const used = Math.max(Number(quota.value.used) || 0, 0);
  if (remain + used <= 0) {
    return [{ value: 1, color: '#e6ebf2' }];
  }
  return [
    { value: remain || 0.0001, color: donutColor.value },
    { value: used || 0.0001, color: '#e6ebf2' },
  ];
});

const modelSegments = computed(() =>
  models.value.length
    ? models.value.map((m, i) => ({
        value: Math.max(m.cost, 0.0001),
        color: colors[i % colors.length],
      }))
    : [{ value: 1, color: '#e6ebf2' }]
);

const kpis = computed(() => {
  const d = data.value;
  const start = startOfWeek();
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  const f = (x) => `${x.getMonth() + 1}/${x.getDate()}`;

  if (!d) {
    return [
      { key: 'total', tone: 'total', icon: WalletOutlined, label: '额度总量', value: '$0.00', sub: '—' },
      { key: 'today', tone: 'today', icon: FireOutlined, label: '今日使用', value: '$0.00', sub: '0 次调用' },
      { key: 'week', tone: 'week', icon: CalendarOutlined, label: '本周使用', value: '$0.00', sub: `${f(start)} – ${f(end)}` },
      { key: 'month', tone: 'month', icon: BarChartOutlined, label: '本月使用', value: '$0.00', sub: '—' },
    ];
  }

  return [
    {
      key: 'total',
      tone: 'total',
      icon: WalletOutlined,
      label: '额度总量',
      value: formatMoney(d.quota.total),
      sub: `${d.user.membership || 'Pro'} · 赠送已用 ${formatMoney(d.quota.gifted)}`,
    },
    {
      key: 'today',
      tone: 'today',
      icon: FireOutlined,
      label: '今日使用',
      value: formatMoney(d.periods.today.cost),
      sub: `${d.periods.today.calls} 次调用`,
    },
    {
      key: 'week',
      tone: 'week',
      icon: CalendarOutlined,
      label: '本周使用',
      value: formatMoney(d.periods.week.cost),
      sub: `${f(start)} – ${f(end)} · ${d.periods.week.calls} 次`,
    },
    {
      key: 'month',
      tone: 'month',
      icon: BarChartOutlined,
      label: '本月使用',
      value: formatMoney(d.periods.month.cost),
      sub: `${new Date().getMonth() + 1}月至今 · ${d.periods.month.calls} 次`,
    },
  ];
});

const columns = [
  { title: '时间', dataIndex: 'timeText', key: 'time' },
  { title: '模型', dataIndex: 'model', key: 'model' },
  { title: '类型', dataIndex: 'kindText', key: 'kind' },
  { title: '额度', dataIndex: 'costText', key: 'cost' },
  { title: 'Token', dataIndex: 'tokenText', key: 'token' },
];

const records = computed(() =>
  (data.value?.events || []).map((e) => ({
    ...e,
    timeText: formatDateTime(e.time),
    kindText: kindLabel(e.kind),
    costText: formatMoney(e.cost),
    tokenText: `In ${formatTokens(e.input)} · Out ${formatTokens(e.output)} · Cache ${formatTokens(e.cache)}`,
  }))
);

function pct(p) {
  return p < 1 ? Number(p).toFixed(1) : Math.round(p);
}

function applyPayload(res) {
  if (res?.data) {
    data.value = res.data;
    if (res.data.heatmap) heatmap.value = res.data.heatmap;
    if (res.error) {
      statusText.value = res.error.message || '部分数据异常';
      statusColor.value = 'warning';
    } else if (res.data.demo) {
      statusText.value = '演示数据 · 登录 Cursor 或设置 Token 后刷新';
      statusColor.value = 'warning';
    } else {
      statusText.value = `已更新 ${new Date(res.updatedAt || Date.now()).toLocaleTimeString()}`;
      statusColor.value = 'success';
    }
  } else {
    statusText.value = res?.error?.message || '暂无数据';
    statusColor.value = 'warning';
  }
}

async function load(force = false) {
  statusText.value = force ? '刷新中…' : '同步中…';
  statusColor.value = 'processing';
  try {
    const res = force ? await seeUtoken.refreshUsage() : await seeUtoken.getUsage(false);
    applyPayload(res);
  } catch (e) {
    statusText.value = e.message || '加载失败';
    statusColor.value = 'error';
  }
}

async function refresh() {
  refreshing.value = true;
  try {
    await load(true);
  } finally {
    refreshing.value = false;
  }
}

async function syncFloatBtn() {
  const s = await seeUtoken.getSettings();
  floatLabel.value = s?.showFloat === false ? '显示悬浮球' : '隐藏悬浮球';
}

async function toggleFloat() {
  const s = await seeUtoken.getSettings();
  await seeUtoken.setSettings({ showFloat: s?.showFloat === false });
  await syncFloatBtn();
}

async function saveToken() {
  await seeUtoken.setSettings({ manualToken: tokenInput.value.trim() });
  tokenOpen.value = false;
  message.success('已保存');
  await refresh();
}

async function clearToken() {
  tokenInput.value = '';
  await seeUtoken.setSettings({ manualToken: '' });
  tokenOpen.value = false;
  await refresh();
}

function goPanels() {
  seeUtoken.openPanels();
}
function hide() {
  seeUtoken.hideDashboard();
}

onMounted(async () => {
  const s = await seeUtoken.getSettings();
  tokenInput.value = s?.manualToken || '';
  await syncFloatBtn();
  await load(false);
  unsub = seeUtoken.onUsageUpdated(applyPayload);
});

onUnmounted(() => {
  if (unsub) unsub();
});
</script>

<style scoped>
.quota-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 100vh;
  padding: 20px 24px 40px;
  background: #f5f7f9;
  box-sizing: border-box;
}

.toolbar,
.panel {
  background: #fff;
  border: 1px solid #e7ebf0;
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
}

.toolbar-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.back-btn {
  color: #64748b;
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
  color: #1f2937;
}

.toolbar-account {
  color: #64748b;
  font-size: 12px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  line-height: 1.4;
}

.toolbar-actions,
.donut-legend {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.panel-sub,
.model-meta {
  margin: 4px 0 0;
  color: #8b95a5;
  font-size: 12px;
  line-height: 1.5;
}

.kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.kpi {
  position: relative;
  overflow: hidden;
  padding: 16px 18px 14px;
  background: #fff;
  border: 1px solid #e7ebf0;
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.kpi-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.kpi-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  font-size: 14px;
  flex-shrink: 0;
}

.kpi.total .kpi-icon {
  color: #1677ff;
  background: #e8f3ff;
}

.kpi.today .kpi-icon {
  color: #d46b08;
  background: #fff7e6;
}

.kpi.week .kpi-icon {
  color: #389e0d;
  background: #f6ffed;
}

.kpi.month .kpi-icon {
  color: #08979c;
  background: #e6fffb;
}

.kpi-label {
  color: #64748b;
  font-size: 13px;
}

.kpi-value {
  margin-top: 8px;
  color: #0f172a;
  font-size: 28px;
  font-weight: 720;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
  line-height: 1.15;
}

.kpi-sub {
  margin-top: 6px;
  color: #8b95a5;
  font-size: 12px;
  line-height: 1.45;
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
  color: #1f2937;
}

.donut-box {
  position: relative;
  height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.donut-value {
  color: #0f172a;
  font-size: 26px;
  font-weight: 720;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.03em;
}

.donut-label {
  margin-top: 2px;
  color: #94a3b8;
  font-size: 12px;
}

.donut-legend {
  justify-content: center;
  color: #64748b;
  font-size: 12px;
  padding: 0 18px;
}

.swatch {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 6px;
  border-radius: 99px;
  background: #1677ff;
}

.swatch.used {
  background: #e6ebf2;
}

.reset-block {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 14px 18px 18px;
  padding: 12px 14px;
  border-radius: 12px;
  background: #f8fafc;
}

.reset-k {
  color: #94a3b8;
  font-size: 12px;
}

.reset-when {
  margin-top: 2px;
  color: #0f172a;
  font-size: 14px;
  font-weight: 650;
}

.reset-left {
  color: #1677ff;
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
  color: #0f172a;
  font-size: 20px;
  font-weight: 720;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.03em;
  line-height: 1.15;
}

.model-pie-label {
  margin-top: 2px;
  color: #94a3b8;
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
  color: #1f2937;
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
  color: #0f172a;
  font-weight: 650;
}

.model-pct {
  color: #94a3b8;
  min-width: 42px;
  text-align: right;
}

.model-bar {
  height: 6px;
  margin: 6px 0 4px 20px;
  border-radius: 99px;
  background: #f1f5f9;
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

.table-wrap {
  padding: 0 12px 8px;
}

.block-empty {
  margin: 0;
  padding: 28px 18px 32px;
  color: #94a3b8;
  text-align: center;
}

@media (max-width: 1100px) {
  .kpis,
  .mid,
  .model-body {
    grid-template-columns: 1fr;
  }
}
</style>
