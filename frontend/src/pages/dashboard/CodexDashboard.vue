<template>
  <div class="quota-page">
    <div class="toolbar dashboard-toolbar">
      <div class="toolbar-main">
        <a-button type="text" aria-label="返回模型额度" @click="seeUtoken.openPanels()">
          <template #icon><ArrowLeftOutlined /></template>
        </a-button>
        <img class="brand" :src="codexLogo" alt="" />
        <strong>Codex</strong>
        <span class="account">{{ data?.user?.email ? maskEmail(data.user.email) : data?.connected ? '本机 Codex 已接入' : '等待本机 Codex 登录' }}</span>
      </div>
      <div class="toolbar-actions">
        <span class="updated">{{ data?.syncing ? '账户额度同步中…' : quotaUpdatedLabel }}</span>
        <div class="refresh-controls">
          <a-select v-model:value="autoRefreshMinutes" class="refresh-interval" size="middle" aria-label="Codex 额度自动刷新间隔" :loading="savingAutoRefresh" :disabled="savingAutoRefresh" @change="saveAutoRefresh">
            <a-select-option :value="0">手动刷新</a-select-option>
            <a-select-option :value="1">每 1 分钟</a-select-option>
            <a-select-option :value="5">每 5 分钟</a-select-option>
            <a-select-option :value="15">每 15 分钟</a-select-option>
            <a-select-option :value="30">每 30 分钟</a-select-option>
          </a-select>
          <a-button class="refresh-now" type="primary" :loading="loading || data?.syncing" @click="refresh(true)">
            <template #icon><ReloadOutlined /></template>立即刷新
          </a-button>
        </div>
      </div>
    </div>

    <a-alert v-if="error || data?.syncError" type="warning" show-icon :message="error || data.syncError" />
    <a-alert v-if="data && !data.connected" type="info" show-icon message="请先在本机 Codex 登录并使用一次，然后点击立即刷新。" />

    <section class="mid">
      <article class="panel quota-panel">
        <header class="panel-head quota-head">
          <div><h3>账户额度</h3></div>
          <span v-if="data?.user?.plan" class="plan">{{ data.user.plan }}</span>
        </header>
        <div class="pool-donuts">
          <div v-for="(item, i) in windows" :key="item.id" class="pool">
            <DonutChart :size="152" :cutout="0.72" :segments="quotaSegments(item, i, 'transparent')" track="#e6ebf2" rounded-caps>
              <template #center>
                <div class="donut-value">{{ quotaText(item) }}</div>
                <div class="muted">{{ item.stale ? '待更新' : item.remainingPercent == null ? '暂无额度' : '剩余' }}</div>
              </template>
            </DonutChart>
            <b class="pool-label">{{ item.label }}</b>
          </div>
        </div>
        <div class="reset-modules">
          <div v-for="item in windows" :key="item.id" class="reset-block">
            <div>
              <div class="reset-k">到期重置 · {{ item.label }}</div>
              <div class="reset-when">{{ item.resetsAt ? formatDateTime(item.resetsAt) : '重置时间未知' }}</div>
            </div>
            <div class="reset-left">{{ item.resetsAt && !item.stale ? formatCountdown(item.resetsAt) : '等待 Codex 更新' }}</div>
          </div>
        </div>
      </article>

      <article class="panel models-panel">
        <header class="panel-head">
          <div>
            <h3>模型 Token 用量</h3>
          </div>
          <a-radio-group v-model:value="period" size="small" button-style="solid">
            <a-radio-button v-for="item in periodOptions" :key="item.key" :value="item.key">{{ item.label }}</a-radio-button>
          </a-radio-group>
        </header>
        <div v-if="models.length" class="model-body">
          <div class="model-chart">
            <DonutChart :size="190" :cutout="0.7" :segments="modelSegments" track="#e6ebf2">
              <template #center><div class="donut-value">{{ formatTokens(totalTokens) }}</div><div class="muted">Token 合计</div></template>
            </DonutChart>
          </div>
          <div class="model-list">
            <div v-for="(m, i) in models" :key="m.model" class="model-row">
              <div class="model-top">
                <i :style="{ background: colors[i % colors.length] }" />
                <b class="model-name">{{ m.model }}</b><b>{{ formatTokens(m.tokens) }}</b><span class="muted">{{ percent(m.tokens) }}%</span>
              </div>
              <div class="model-track"><span :style="{ width: `${m.tokens / (totalTokens || 1) * 100}%`, background: colors[i % colors.length] }" /></div>
              <p class="model-meta">{{ m.calls }} 次 · 输入 {{ formatTokens(m.input) }} · 输出 {{ formatTokens(m.output) }} · 缓存读写 {{ formatTokens(m.cache) }}</p>
            </div>
          </div>
        </div>
        <div v-else class="empty">{{ loading ? '正在读取本机用量…' : '该时段暂无模型用量记录' }}</div>
      </article>
    </section>

    <section class="panel usage-records codex-records">
      <header class="panel-head"><h3>使用记录</h3></header>
      <div class="table-wrap">
        <a-table
          :columns="columns"
          :data-source="records"
          row-key="id"
          size="small"
          table-layout="fixed"
          :pagination="{ pageSize: 8, showSizeChanger: false, hideOnSinglePage: true }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'time'">{{ formatDateTime(record.time) }}</template>
            <template v-if="column.key === 'prompt'">
              <span class="question-content" :title="record.prompt || undefined">{{ record.prompt || '—' }}</span>
            </template>
            <template v-if="column.key === 'tokens'">
              <div class="token-cell">
                <span class="token-part"><em>输入（不含缓存）</em> {{ formatTokens(record.input) }}</span>
                <span class="token-part"><em>输出</em> {{ formatTokens(record.output) }}</span>
                <span class="token-part"><em>缓存读写</em> {{ formatTokens(record.cache) }}</span>
              </div>
            </template>
          </template>
        </a-table>
      </div>
    </section>
    <HeatmapBoard v-model="heatmap" provider="codex" />
    <UsageTrendBoard :heatmap="heatmap" />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { message } from 'ant-design-vue';
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons-vue';
import { seeUtoken } from '../../bridge';
import DonutChart from '../../components/DonutChart.vue';
import HeatmapBoard from '../../components/HeatmapBoard.vue';
import UsageTrendBoard from '../../components/UsageTrendBoard.vue';
import codexLogo from '../../assets/brand/codex-logo.svg';
import { formatTokens, formatDateTime, formatCountdown, maskEmail } from '../../utils/format';
import { quotaText, quotaSegments, useCodexUsage } from '../../utils/codex';

const { data, loading, error, refresh, year } = useCodexUsage(false);
const heatmap = ref(null);
const autoRefreshMinutes = ref(1);
const savingAutoRefresh = ref(false);
let savedAutoRefreshMinutes = 1;
async function saveAutoRefresh(minutes) {
  savingAutoRefresh.value = true;
  try {
    await seeUtoken.setSettings({ codexAutoRefreshMinutes: Number(minutes) });
    savedAutoRefreshMinutes = Number(minutes);
    await refresh();
  } catch (e) {
    autoRefreshMinutes.value = savedAutoRefreshMinutes;
    message.error(e?.message || '刷新间隔保存失败');
  } finally {
    savingAutoRefresh.value = false;
  }
}
const period = ref('week');
const periodOptions = [{ key: 'today', label: '今日' }, { key: 'week', label: '本周' }, { key: 'month', label: '本月' }, { key: 'all', label: '全部' }];
const colors = ['#10a37f', '#1677ff', '#69b1ff', '#73d13d', '#36cfc9', '#597ef7'];
const windows = computed(() => data.value?.windows || [{ id: 'primary', label: '短期额度' }, { id: 'secondary', label: '长期额度' }]);
const models = computed(() => data.value?.models?.[period.value] || []);
const periodData = computed(() => data.value?.periods?.[period.value] || {});
const totalTokens = computed(() => periodData.value.tokens || 0);
const modelSegments = computed(() => models.value.map((m, i) => ({ value: m.tokens, color: colors[i % colors.length] })));
const records = computed(() => data.value?.events || []);
const quotaUpdatedLabel = computed(() => data.value?.quotaUpdatedAt ? `更新时间 ${new Date(data.value.quotaUpdatedAt).toLocaleTimeString('zh-CN')}` : '等待额度同步');
const columns = [
  { title: '时间', key: 'time', width: 164, ellipsis: true },
  { title: '模型', dataIndex: 'model', width: 132, ellipsis: true },
  { title: '使用项目', dataIndex: 'project', width: 100, ellipsis: true },
  { title: '会话内容', dataIndex: 'prompt', key: 'prompt', width: 172, ellipsis: true },
  { title: 'Token', key: 'tokens', className: 'col-token' },
];
function percent(tokens) { return ((tokens / (totalTokens.value || 1)) * 100).toFixed(1); }
watch(data, d => {
  if (d?.heatmap) heatmap.value = d.heatmap;
  if (!savingAutoRefresh.value && [0, 1, 5, 15, 30].includes(d?.autoRefreshMinutes)) {
    autoRefreshMinutes.value = d.autoRefreshMinutes;
    savedAutoRefreshMinutes = d.autoRefreshMinutes;
  }
});
watch(heatmap, h => { if (h?.year) year.value = h.year; });
</script>

<style scoped>
.quota-page { min-height: 100vh; padding: 20px 24px 32px; background: var(--sut-bg, #f5f7f9); display: flex; flex-direction: column; gap: 16px; color: var(--sut-text, #0f172a); }
.toolbar, .panel { background: var(--sut-surface, #fff); border: 1px solid var(--sut-border, #e7ebf0); border-radius: 14px; box-shadow: 0 1px 2px #0f172a0a; }
.toolbar { padding: 14px 18px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.toolbar-main, .toolbar-actions { display: flex; align-items: center; gap: 12px; }
.toolbar-actions { margin-left: auto; flex-wrap: wrap; }
.brand { width: 28px; height: 28px; object-fit: contain; }
.toolbar strong { font-size: 18px; }
.account { color: var(--sut-secondary, #64748b); font-size: 13px; }
.plan { color: var(--sut-text, #1f2937); font-size: 12px; line-height: 22px; white-space: nowrap; text-transform: capitalize; }
.updated { color: var(--sut-muted, #94a3b8); font-size: 12px; }
.mid { display: grid; grid-template-columns: minmax(360px, .9fr) minmax(0, 1.8fr); gap: 16px; }
.panel-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; padding: 18px 20px 10px; flex-wrap: wrap; }
.quota-head { align-items: center; }
h3 { margin: 0; color: var(--sut-text, #1f2937); font-size: 15px; font-weight: 650; }
.pool-donuts { padding: 24px 12px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.pool { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.donut-value { font-size: 23px; font-weight: 700; font-variant-numeric: tabular-nums; }
.muted { color: var(--sut-muted, #94a3b8); font-size: 12px; margin-top: 4px; }
.pool-label { margin-top: 6px; font-size: 13px; }
.reset-modules { display: flex; flex-direction: column; gap: 10px; margin: 0 18px 14px; }
.reset-block { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border-radius: 12px; background: var(--sut-inset, #f8fafc); }
.reset-k { color: var(--sut-muted, #94a3b8); font-size: 12px; }
.reset-when { margin-top: 2px; color: var(--sut-text, #0f172a); font-size: 14px; font-weight: 650; }
.reset-left { color: var(--sut-primary, #1677ff); font-size: 13px; font-weight: 650; flex-shrink: 0; }
.model-body { display: flex; gap: 20px; align-items: center; padding: 20px; min-height: 260px; }
.model-chart { flex-shrink: 0; }
.model-list { flex: 1; min-width: 0; max-height: 300px; overflow: auto; }
.model-row + .model-row { margin-top: 18px; }
.model-top { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.model-top i { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.model-name { flex: 1; overflow: hidden; text-overflow: ellipsis; }
.model-track { height: 6px; border-radius: 6px; background: var(--sut-track, #f1f5f9); overflow: hidden; margin: 7px 0 0 18px; }
.model-track span { display: block; height: 100%; border-radius: 6px; }
.model-meta { margin: 7px 0 0 18px; font-size: 11px; color: var(--sut-muted, #94a3b8); line-height: 1.6; }
.empty { padding: 90px 20px; text-align: center; color: var(--sut-muted, #94a3b8); }
@media (max-width: 1100px) { .mid { grid-template-columns: 1fr; } .model-body { min-height: 220px; } }
@media (max-width: 720px) { .quota-page { padding: 12px; } .model-body { flex-direction: column; align-items: stretch; } .model-chart { align-self: center; } .account { display: none; } }
</style>
