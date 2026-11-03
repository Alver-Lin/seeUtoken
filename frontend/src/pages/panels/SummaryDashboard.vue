<template>
  <div class="summary-dashboard">
    <a-alert v-if="error" type="warning" show-icon :message="error" />

    <section class="panel">
      <header class="panel-head">
        <h3>模型 Token 用量</h3>
        <a-radio-group v-model:value="period" size="small" button-style="solid">
          <a-radio-button v-for="item in periods" :key="item.key" :value="item.key">{{ item.label }}</a-radio-button>
        </a-radio-group>
      </header>
      <div class="usage-totals">
        <div><span>Token 合计</span><b>{{ formatTokensExact(totals.tokens) }}</b></div>
        <div><span>调用次数</span><b :title="callCountTitle(totals)">{{ callCountText(totals) }}</b></div>
        <div><span>使用模型</span><b>{{ models.length }}</b></div>
        <div><span>有用量的工具</span><b>{{ activeProviders.length }}</b></div>
      </div>
      <div v-if="models.length" class="model-body">
        <DonutChart :size="184" :cutout="0.72" :segments="segments" track="#e6ebf2">
          <template #center><b class="chart-total">{{ formatTokens(totals.tokens) }}</b><div class="muted">Token 合计</div></template>
        </DonutChart>
        <div class="model-list">
          <div v-for="(model, index) in models" :key="model.model" class="model-row">
            <div class="model-top">
              <i :style="{ background: colors[index % colors.length] }" />
              <b class="model-name">{{ model.model }}</b>
              <span class="muted">{{ model.providers.map(providerLabel).join(' · ') }}</span>
              <b :title="formatTokensExact(model.tokens)">{{ formatTokens(model.tokens) }}</b>
              <span class="model-percent">{{ model.percent.toFixed(1) }}%</span>
            </div>
            <div class="model-track"><span :style="{ width: `${model.percent}%`, background: colors[index % colors.length] }" /></div>
            <p><span v-if="model.calls != null || model.knownCalls > 0" :title="callCountTitle(model)">{{ callCountText(model) }} 次 · </span>输入 {{ formatTokens(model.input) }} · 输出 {{ formatTokens(model.output) }} · 缓存 {{ formatTokens(model.cache) }}</p>
          </div>
        </div>
      </div>
      <p v-else class="empty">{{ loading ? '正在汇总用量…' : '该时段暂无模型用量记录' }}</p>
    </section>

    <section class="panel usage-records">
      <header class="panel-head"><h3>使用记录</h3><span class="muted">各工具近期明细 · 按时间倒序</span></header>
      <div class="table-wrap">
        <a-table :columns="columns" :data-source="data?.events || []" row-key="id" size="small" table-layout="fixed" :loading="loading && !data" :pagination="{ pageSize: 8, showSizeChanger: false, hideOnSinglePage: true }" :scroll="{ x: 1050 }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'time'">{{ formatDateTime(record.time) }}</template>
            <template v-else-if="column.key === 'provider'">{{ providerLabel(record.provider) }}</template>
            <template v-else-if="column.key === 'project'">{{ record.project || '—' }}</template>
            <template v-else-if="column.key === 'prompt'"><span class="question-content" :title="record.prompt || undefined">{{ record.prompt || '—' }}</span></template>
            <template v-else-if="column.key === 'tokens'">
              <div class="token-cell">
                <span class="token-part" title="输入（不含缓存）"><em>输入</em> {{ formatTokens(record.input) }}</span>
                <span class="token-part"><em>输出</em> {{ formatTokens(record.output) }}</span>
                <span class="token-part"><em>缓存</em> {{ formatTokens(record.cache) }}</span>
              </div>
            </template>
          </template>
        </a-table>
      </div>
    </section>
    <HeatmapBoard v-model="heatmap" :load-year="loadYear" />
    <UsageTrendBoard :heatmap="data?.heatmap" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { seeUtoken } from '../../bridge';
import DonutChart from '../../components/DonutChart.vue';
import HeatmapBoard from '../../components/HeatmapBoard.vue';
import UsageTrendBoard from '../../components/UsageTrendBoard.vue';
import { formatDateTime, formatTokens, formatTokensExact } from '../../utils/format';

const props = defineProps({ includeCachedTokens: Boolean });
const data = ref(null);
const heatmap = ref(null);
const selectedYear = ref(new Date().getFullYear());
const loading = ref(false);
const error = ref('');
const updatedAt = ref(null);
const period = ref('all');
const periods = [{ key: 'today', label: '今日' }, { key: 'week', label: '本周' }, { key: 'month', label: '本月' }, { key: 'all', label: '全部' }];
const colors = ['#1677ff', '#10a37f', '#69b1ff', '#73d13d', '#36cfc9', '#597ef7'];
const models = computed(() => data.value?.models?.[period.value] || []);
const totals = computed(() => data.value?.periods?.[period.value] || {});
const activeProviders = computed(() => [...new Set(models.value.flatMap(model => model.providers))]);
const segments = computed(() => models.value.map((model, index) => ({ value: model.tokens, color: colors[index % colors.length] })));
const columns = [
  { title: '时间', key: 'time', width: 164, ellipsis: true },
  { title: '工具', key: 'provider', width: 80 },
  { title: '模型', dataIndex: 'model', width: 132, ellipsis: true },
  { title: '使用项目', key: 'project', width: 100, ellipsis: true },
  { title: '会话内容', key: 'prompt', width: 172, ellipsis: true },
  { title: 'Token', key: 'tokens', className: 'col-token' },
];
function providerLabel(provider) { return ({ cursor: 'Cursor', codex: 'Codex', qoder: 'Qoder' })[provider] || provider; }
function callCountText(usage) {
  if (usage.calls != null) return formatTokensExact(usage.calls);
  return usage.knownCalls > 0 ? `≥ ${formatTokensExact(usage.knownCalls)}` : '—';
}
function callCountTitle(usage) {
  return usage.calls == null ? '部分工具未提供调用次数，展示已知次数下限' : undefined;
}
let timer;
let unsubscribe;
let stopped = false;
let pending = false;
let refreshAgain = false;
async function refresh(force = false) {
  if (pending) { refreshAgain = true; return; }
  pending = true;
  loading.value = true;
  try {
    const payload = await seeUtoken.getSummaryUsage(new Date().getFullYear(), force);
    if (stopped) return;
    if (!payload?.data) throw new Error('汇总记录暂未就绪');
    data.value = payload.data;
    updatedAt.value = payload.updatedAt;
    if (selectedYear.value === payload.data.heatmap?.year) heatmap.value = payload.data.heatmap;
    error.value = '';
  } catch (e) {
    if (!stopped) error.value = e?.message || '汇总记录读取失败';
  } finally {
    pending = false;
    loading.value = false;
    if (!stopped && refreshAgain) { refreshAgain = false; refresh(); }
  }
}
async function loadYear(year) {
  const previousYear = selectedYear.value;
  selectedYear.value = year;
  try {
    const payload = await seeUtoken.getSummaryUsage(year);
    if (!payload?.data?.heatmap) throw new Error('热力图读取失败');
    return payload.data.heatmap;
  } catch (e) { selectedYear.value = previousYear; throw e; }
}
watch(() => props.includeCachedTokens, async () => {
  await refresh();
  if (selectedYear.value !== new Date().getFullYear()) {
    try { heatmap.value = await loadYear(selectedYear.value); } catch (e) { error.value = e.message; }
  }
});
onMounted(() => {
  refresh();
  timer = window.setInterval(() => refresh(), 30000);
  unsubscribe = seeUtoken.onUsageUpdated(() => refresh());
});
onUnmounted(() => { stopped = true; clearInterval(timer); unsubscribe?.(); });
defineExpose({ refresh, loading, updatedAt });
</script>

<style scoped>
.summary-dashboard { display: flex; flex-direction: column; gap: 16px; color: var(--sut-text); }
.panel-head { display: flex; justify-content: space-between; align-items: center; gap: 14px; flex-wrap: wrap; }
.muted { font-size: 12px; color: var(--sut-muted); }
.panel { background: var(--sut-surface); border: 1px solid var(--sut-border); border-radius: 14px; overflow: hidden; }
.panel-head { padding: 14px 18px 8px; }
h3 { margin: 0; font-size: 15px; font-weight: 650; }
.usage-totals { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 10px 18px 0; padding: 16px 18px; background: var(--sut-inset); border-radius: 10px; }
.usage-totals div { display: flex; flex-direction: column; gap: 6px; }
.usage-totals span { font-size: 12px; color: var(--sut-secondary); }
.usage-totals b { font-size: 24px; font-variant-numeric: tabular-nums; }
.model-body { display: flex; align-items: center; gap: 36px; padding: 24px 28px; }
.chart-total { font-size: 24px; }
.model-list { flex: 1; min-width: 0; max-height: 340px; overflow-y: auto; padding-right: 8px; }
.model-row + .model-row { margin-top: 18px; }
.model-top { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.model-top i { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.model-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.model-percent { min-width: 48px; text-align: right; color: var(--sut-secondary); }
.model-track { height: 6px; margin: 8px 0; border-radius: 6px; background: var(--sut-track); overflow: hidden; }
.model-track span { display: block; height: 100%; border-radius: inherit; }
.model-row p { margin: 0; font-size: 12px; color: var(--sut-secondary); }
.empty { padding: 28px 18px; text-align: center; color: var(--sut-muted); }
@media (max-width: 760px) {
  .usage-totals { grid-template-columns: repeat(2, 1fr); }
  .model-body { flex-direction: column; padding: 20px 18px; gap: 20px; }
  .model-list { width: 100%; }
  .model-top { flex-wrap: wrap; }
}
</style>
