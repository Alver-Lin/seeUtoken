<template>
  <div class="quota-home">
    <ModalContext />
    <div class="toolbar">
      <div>
        <div class="toolbar-title">模型额度</div>
      </div>
      <div class="toolbar-actions">
        <a-button
          type="default"
          class="settings-btn"
          aria-label="设置"
          @click="settingsOpen = true"
        >
          <template #icon><SettingOutlined /></template>
        </a-button>
        <a-button
          type="primary"
          :disabled="!panelsLoaded || availableProviders.length === 0"
          :title="!panelsLoaded ? '正在加载已添加的软件' : availableProviders.length === 0 ? '所有软件均已添加，删除面板后可重新添加' : '每个软件只能添加一个额度面板'"
          @click="openCreate"
        >
          <template #icon><PlusOutlined /></template>
          新建额度面板
        </a-button>
      </div>
    </div>

    <section class="panel-grid">
      <article
        v-for="panel in panels"
        :key="panel.id"
        class="quota-card"
        @click="goPanel(panel)"
      >
        <header class="card-top">
          <div class="card-brand">
            <span class="card-icon" :class="panel.type">
              <img
                v-if="providerIcon(panel.type)"
                class="card-logo"
                :src="providerIcon(panel.type)"
                alt=""
              />
              <ThunderboltOutlined v-else />
            </span>
            <div>
              <div class="card-name">{{ panel.name }}</div>
            </div>
          </div>
          <a-button
            type="text"
            size="small"
            class="card-delete"
            @click="confirmRemove(panel, $event)"
          >
            <template #icon><DeleteOutlined /></template>
          </a-button>
        </header>

        <div class="card-mid">
          <template v-if="cardMeta(panel).connected">
            <div class="card-stats">
              <div class="card-token-basis">{{ tokenBasisLabel(includeCachedTokens) }}</div>
              <div class="card-stat-row">
                <span class="card-stat-label">当日 Token</span>
                <span class="card-stat-v" :title="cardMeta(panel).todayTokensExact">{{
                  cardMeta(panel).todayTokensText
                }}</span>
              </div>
              <div class="card-stat-row">
                <span class="card-stat-label">{{ panel.type === 'codex' ? '本周 Token' : '本周期 Token' }}</span>
                <span class="card-stat-v" :title="cardMeta(panel).cycleTokensExact">{{
                  cardMeta(panel).cycleTokensText
                }}</span>
              </div>
            </div>
            <div class="card-pool">
              <DonutChart
                :size="112"
                :cutout="0.72"
                :segments="cardMeta(panel).cursorSegments"
                :rounded-caps="panel.type === 'codex'"
                track="#e6ebf2"
              >
                <template #center>
                  <div class="pool-pct">{{ cardMeta(panel).cursorRemainText }}</div>
                </template>
              </DonutChart>
              <div class="pool-name">{{ panel.type === 'codex' ? codexData?.windows?.[0]?.label || '短期额度' : 'Cursor 模型' }}</div>
            </div>
            <div class="card-pool">
              <DonutChart
                :size="112"
                :cutout="0.72"
                :segments="cardMeta(panel).otherSegments"
                :rounded-caps="panel.type === 'codex'"
                track="#e6ebf2"
              >
                <template #center>
                  <div class="pool-pct">{{ cardMeta(panel).otherRemainText }}</div>
                </template>
              </DonutChart>
              <div class="pool-name">{{ panel.type === 'codex' ? codexData?.windows?.[1]?.label || '长期额度' : '其余模型' }}</div>
            </div>
          </template>
          <div v-else class="card-empty">
            <div class="card-remain">{{ cardMeta(panel).remainText }}</div>
            <div class="card-label">待连接</div>
          </div>
        </div>

        <div class="card-foot">
          <span>{{ cardMeta(panel).planText }}</span>
          <span v-if="cardMeta(panel).updatedText">更新 {{ cardMeta(panel).updatedText }}</span>
        </div>
      </article>
    </section>

    <a-modal
      v-model:open="settingsOpen"
      title="设置"
      :footer="null"
      :style="{ top: '6vh' }"
      :body-style="{ maxHeight: 'calc(88vh - 110px)', overflowY: 'auto' }"
      @cancel="settingsOpen = false"
    >
      <div class="settings-modal">
        <section class="settings-section">
          <div class="settings-section-title">Token 统计口径</div>
          <div class="float-settings-row">
            <div>
              <div class="float-settings-label">Token 统计口径是否包含缓存</div>
              <div class="float-settings-desc">开启后统计输入、输出和缓存；关闭时仅统计输入＋输出。切换后自动保存。</div>
            </div>
            <a-switch
              aria-label="Token 统计口径是否包含缓存"
              :checked="includeCachedTokens"
              :loading="floatSettingsSaving"
              :disabled="floatSettingsSaving"
              @change="onIncludeCachedTokensChange"
            />
          </div>
        </section>
        <section class="settings-section">
          <div class="settings-section-title">外观</div>
          <div class="float-settings-row float-settings-row-stack">
            <div>
              <div class="float-settings-label">外观模式</div>
              <div class="float-settings-desc">统一设置首页、详情大屏、侧边用量栏与弹窗的外观，切换后自动保存</div>
            </div>
            <a-select
              :value="floatGlassStyle"
              class="glass-style-select"
              aria-label="外观模式"
              :options="FLOAT_APPEARANCE_OPTIONS"
              :loading="floatSettingsSaving"
              :disabled="floatSettingsSaving"
              @change="onFloatGlassStyleChange"
            />
          </div>
        </section>
        <section class="settings-section">
          <div class="settings-section-title">侧边用量栏</div>
          <div class="float-settings-row">
            <div>
              <div class="float-settings-label">显示侧边用量栏</div>
              <div class="float-settings-desc">关闭后仍可从系统托盘打开主窗口</div>
            </div>
            <a-switch
              aria-label="显示侧边用量栏"
              :checked="showFloat"
              :loading="floatSettingsSaving"
              :disabled="floatSettingsSaving"
              @change="onShowFloatChange"
            />
          </div>
          <div class="float-settings-row">
            <div>
              <div class="float-settings-label">贴边自动缩进</div>
              <div class="float-settings-desc">{{ supportsNativeDocking ? '靠近屏幕左右边缘后移出鼠标收起，悬停展开（macOS）' : '当前平台支持拖动与置顶，贴边自动缩进仅适用于 macOS' }}</div>
            </div>
            <a-switch
              aria-label="贴边自动缩进"
              :checked="supportsNativeDocking && floatAutoHide"
              :loading="floatSettingsSaving"
              :disabled="floatSettingsSaving || !supportsNativeDocking"
              @change="onFloatBehaviorChange('floatAutoHide', $event)"
            />
          </div>
          <div class="float-settings-row">
            <div>
              <div class="float-settings-label">始终置顶</div>
              <div class="float-settings-desc">让侧边用量栏始终显示在其他窗口上方</div>
            </div>
            <a-switch
              aria-label="始终置顶"
              :checked="floatAlwaysOnTop"
              :loading="floatSettingsSaving"
              :disabled="floatSettingsSaving"
              @change="onFloatBehaviorChange('floatAlwaysOnTop', $event)"
            />
          </div>
        </section>
      </div>
    </a-modal>

    <a-modal
      v-model:open="createOpen"
      title="新建额度面板"
      ok-text="创建并进入"
      cancel-text="取消"
      :confirm-loading="creating"
      :ok-button-props="{ disabled: !canCreatePanel }"
      @ok="createPanel"
    >
      <div class="create-form">
        <label class="field">
          <span>服务商</span>
          <a-select v-model:value="formProvider" :disabled="creating" style="width: 100%">
            <a-select-option
              v-for="item in QUOTA_PROVIDERS"
              :key="item.value"
              :value="item.value"
              :disabled="addedProviders.has(item.value)"
            >
              <span class="provider-option">
                <img
                  v-if="providerIcon(item.value)"
                  class="provider-option-icon"
                  :src="providerIcon(item.value)"
                  alt=""
                />
                <ThunderboltOutlined v-else class="provider-option-fallback" />
                {{ item.label }}{{ addedProviders.has(item.value) ? '（已添加）' : '' }}
              </span>
            </a-select-option>
          </a-select>
        </label>
        <p class="hint">{{ createHint }}</p>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { message, Modal } from 'ant-design-vue';
import {
  PlusOutlined,
  ThunderboltOutlined,
  DeleteOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue';
import cursorLogo from '../../assets/brand/cursor-logo.svg';
import codexLogo from '../../assets/brand/codex-logo.svg';
import qoderLogo from '../../assets/brand/qoder-logo.svg';
import { seeUtoken } from '../../bridge';
import DonutChart from '../../components/DonutChart.vue';
import { codexPlanLabel, quotaSegments, quotaText, useCodexUsage } from '../../utils/codex';
import { formatPercent, formatTokens, formatTokensExact } from '../../utils/format';
import { applyMainAppearance } from '../../utils/mainAppearance';
import { tokenBasisLabel } from '../../utils/tokenAccounting';
import {
  DEFAULT_FLOAT_GLASS_STYLE,
  FLOAT_APPEARANCE_OPTIONS,
  normalizeFloatGlassStyle,
} from '../../constants/floatGlass';

const [modal, ModalContext] = Modal.useModal();

const QUOTA_PROVIDERS = [
  { value: 'cursor', label: 'Cursor' },
  { value: 'codex', label: 'Codex' },
  { value: 'qoder', label: 'Qoder' },
];

const DEFAULT_PANELS = [
  { id: 'cursor-default', type: 'cursor', name: 'Cursor', createdAt: 0 },
  { id: 'codex-default', type: 'codex', name: 'Codex', createdAt: 0 },
  { id: 'qoder-default', type: 'qoder', name: 'Qoder', createdAt: 0 },
];

const panels = ref([...DEFAULT_PANELS]);
const panelsLoaded = ref(false);
const addedProviders = computed(() => new Set(panels.value.map(panel => panel.type || panel.provider || 'cursor')));
const availableProviders = computed(() => QUOTA_PROVIDERS.filter(item => !addedProviders.value.has(item.value)));
const { data: codexData, refresh: refreshCodex } = useCodexUsage();
// 同步读 HTML bootstrap / 已推送缓存，首帧就不要「未连接」
const usagePayload = ref(
  typeof window !== 'undefined' && window.__seeUtokenLastCard
    ? window.__seeUtokenLastCard
    : null
);
const createOpen = ref(false);
const creating = ref(false);
const formProvider = ref(null);
const canCreatePanel = computed(() => panelsLoaded.value && !creating.value &&
  availableProviders.value.some(item => item.value === formProvider.value));
const settingsOpen = ref(false);
const showFloat = ref(true);
const floatAutoHide = ref(true);
const supportsNativeDocking = window.__seeUtokenFloatSettings?.platform
  ? window.__seeUtokenFloatSettings.platform === 'darwin'
  : /Macintosh|Mac OS X/.test(navigator.userAgent);
const floatAlwaysOnTop = ref(true);
const floatExpanded = ref(false);
const floatSettingsSaving = ref(false);
const floatGlassStyle = ref(DEFAULT_FLOAT_GLASS_STYLE);
const includeCachedTokens = ref(!!usagePayload.value?.data?.includeCachedTokens);
let unsub = null;

const createHint = computed(() => {
  if (!availableProviders.value.length) return '所有软件均已添加，删除面板后可重新添加。';
  if (addedProviders.value.has(formProvider.value)) return '该软件已添加，每个软件只能添加一个额度面板。';
  if (formProvider.value === 'cursor') {
    return '创建后进入面板，可登录 Cursor 并实时同步额度。';
  }
  if (formProvider.value === 'codex') return '自动识别本机 Codex 登录，展示账户额度、Token 统计和详情大屏。';
  const label = QUOTA_PROVIDERS.find((i) => i.value === formProvider.value)?.label || '';
  return `创建后进入面板。${label} 额度接入即将支持。`;
});

function providerIcon(provider) {
  if (provider === 'cursor') return cursorLogo;
  if (provider === 'codex') return codexLogo;
  if (provider === 'qoder') return qoderLogo;
  return '';
}

function providerLabel(provider) {
  return QUOTA_PROVIDERS.find((i) => i.value === provider)?.label || provider;
}

function uid() {
  return `panel-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

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

function isDemoFlag(v) {
  return v === true || v === 'true' || v === 1 || v === '1';
}

function periodTokenCount(data, periodKey) {
  if (!data || typeof data !== 'object') return null;
  const fromUsage = data.usageTokens?.[periodKey];
  if (fromUsage != null && Number.isFinite(Number(fromUsage))) {
    return Number(fromUsage);
  }
  const p = data.periods?.[periodKey];
  if (!p || typeof p !== 'object') return null;
  const total = Number(p.tokens ?? ((Number(p.input) || 0) + (Number(p.output) || 0)));
  if (
    total <= 0 &&
    !(Number(p.cost) > 0 || Number(p.calls) > 0 || Number(p.input) > 0 || Number(p.output) > 0)
  ) {
    return null;
  }
  return total;
}

function tokenCountText(data, periodKey) {
  const n = periodTokenCount(data, periodKey);
  return n == null ? '—' : formatTokens(n);
}

function tokenCountExact(data, periodKey) {
  const n = periodTokenCount(data, periodKey);
  return n == null ? '' : `${formatTokensExact(n)} Token（${tokenBasisLabel(data?.includeCachedTokens)}）`;
}

function isRealCursorUsage(data) {
  if (!data || isDemoFlag(data.demo)) return false;
  const q = data.quota;
  if (!q || typeof q !== 'object') return false;
  return !!(
    data.user?.email ||
    data.authSource ||
    q.autoPercent != null ||
    q.cursorModelsPercent != null ||
    q.usedPercent != null ||
    Number(q.total) > 0
  );
}

function cardMeta(panel) {
  if (panel.type === 'codex') {
    const d = codexData.value;
    return {
      connected: !!d?.connected,
      remainText: d ? '未连接' : '同步中…',
      planText: d?.connected ? codexPlanLabel(d.user?.plan, d.syncing) : '点击查看接入状态',
      updatedText: d?.quotaUpdatedAt ? new Date(d.quotaUpdatedAt).toLocaleTimeString('zh-CN') : '',
      cursorSegments: quotaSegments(d?.windows?.[0], 0, 'transparent'),
      otherSegments: quotaSegments(d?.windows?.[1], 1, 'transparent'),
      cursorRemainText: quotaText(d?.windows?.[0]),
      otherRemainText: quotaText(d?.windows?.[1]),
      todayTokensText: d ? formatTokens(d.usageTokens.today) : '—',
      cycleTokensText: d ? formatTokens(d.usageTokens.week) : '—',
      todayTokensExact: d ? `${formatTokensExact(d.usageTokens.today)} Token（${tokenBasisLabel(d.includeCachedTokens)}；本机记录）` : '',
      cycleTokensExact: d ? `${formatTokensExact(d.usageTokens.week)} Token（${tokenBasisLabel(d.includeCachedTokens)}；本地时间周一至今）` : '',
    };
  }
  if (panel.type !== 'cursor') {
    return {
      remainText: '未接入',
      planText: '额度接入即将支持',
      updatedText: '',
      connected: false,
      cursorSegments: [{ value: 1, color: 'transparent' }],
      otherSegments: [{ value: 1, color: 'transparent' }],
      cursorRemainText: '—',
      otherRemainText: '—',
      todayTokensText: '—',
      cycleTokensText: '—',
      todayTokensExact: '',
      cycleTokensExact: '',
    };
  }

  const data = usagePayload.value?.data;
  const q = data?.quota;

  if (!isRealCursorUsage(data)) {
    return {
      remainText: '未连接',
      planText: '点击卡片登录 Cursor 并同步',
      updatedText: '',
      connected: false,
      cursorSegments: [{ value: 1, color: 'transparent' }],
      otherSegments: [{ value: 1, color: 'transparent' }],
      cursorRemainText: '—',
      otherRemainText: '—',
      todayTokensText: '—',
      cycleTokensText: '—',
      todayTokensExact: '',
      cycleTokensExact: '',
    };
  }

  const cursorUsed = Number(q.cursorModelsPercent ?? q.autoPercent) || 0;
  const otherUsed = Number(q.otherModelsPercent ?? q.apiPercent) || 0;
  const cursorRemain = Math.max(0, 100 - cursorUsed);
  const otherRemain = Math.max(0, 100 - otherUsed);
  const membership = data.user?.membership || 'Pro';
  const ts = usagePayload.value?.updatedAt || data.fetchedAt;
  const updatedText = ts
    ? new Date(ts).toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : '';

  return {
    remainText: '',
    planText: membership,
    updatedText,
    connected: true,
    cursorSegments: poolSegments(cursorUsed, poolColor(cursorUsed)),
    otherSegments: poolSegments(
      otherUsed,
      poolColor(otherUsed) === '#1677ff' ? '#13c2c2' : poolColor(otherUsed)
    ),
    cursorRemainText: formatPercent(cursorRemain),
    otherRemainText: formatPercent(otherRemain),
    todayTokensText: tokenCountText(data, 'today'),
    cycleTokensText: tokenCountText(data, 'cycle'),
    todayTokensExact: tokenCountExact(data, 'today'),
    cycleTokensExact: tokenCountExact(data, 'cycle'),
  };
}

async function persist() {
  await seeUtoken.setSettings({ panels: panels.value });
}

function applyFloatSettings(s) {
  applyMainAppearance(s);
  includeCachedTokens.value = !!s?.includeCachedTokens;
  showFloat.value = s?.showFloat !== false;
  floatAutoHide.value = s?.floatAutoHide !== false;
  floatAlwaysOnTop.value = s?.floatAlwaysOnTop !== false;
  floatExpanded.value = s?.floatCollapsed === false;
  floatGlassStyle.value = normalizeFloatGlassStyle(s?.floatGlassStyle);
}

async function onIncludeCachedTokensChange(checked) {
  const previous = includeCachedTokens.value;
  includeCachedTokens.value = !!checked;
  floatSettingsSaving.value = true;
  try {
    applyFloatSettings(await seeUtoken.setSettings({ includeCachedTokens: !!checked }));
    await refreshCodex();
    seeUtoken.getUsageSummary().then(applyUsage).catch(() => {});
  } catch (err) {
    includeCachedTokens.value = previous;
    message.error(err?.message || '保存失败');
  } finally {
    floatSettingsSaving.value = false;
  }
}

async function loadPanels() {
  const s = await seeUtoken.getSettings();
  applyFloatSettings(s);
  if (Array.isArray(s?.panels)) {
    panels.value = s.panels.map((p) => ({
      ...p,
      type: p.type || p.provider || 'cursor',
    }));
  } else {
    panels.value = [...DEFAULT_PANELS];
    await persist();
  }
  panelsLoaded.value = true;
}

async function onFloatGlassStyleChange(value) {
  const style = normalizeFloatGlassStyle(value);
  const previousStyle = floatGlassStyle.value;
  floatGlassStyle.value = style;
  floatSettingsSaving.value = true;
  try {
    const s = await seeUtoken.setSettings({ floatGlassStyle: style });
    applyFloatSettings(s);
    message.success('已更新全局外观');
  } catch (err) {
    floatGlassStyle.value = previousStyle;
    message.error(err?.message || '保存失败');
  } finally {
    floatSettingsSaving.value = false;
  }
}

async function onShowFloatChange(checked) {
  floatSettingsSaving.value = true;
  try {
    const s = await seeUtoken.setSettings({ showFloat: !!checked });
    applyFloatSettings(s);
    message.success(checked ? '已显示侧边悬浮球' : '已隐藏侧边悬浮球');
  } catch (err) {
    message.error(err?.message || '保存失败');
  } finally {
    floatSettingsSaving.value = false;
  }
}

async function onFloatBehaviorChange(key, checked) {
  floatSettingsSaving.value = true;
  try {
    const s = await seeUtoken.setSettings({ [key]: !!checked });
    applyFloatSettings(s);
    message.success('已更新侧边用量栏设置');
  } catch (err) {
    message.error(err?.message || '保存失败');
  } finally {
    floatSettingsSaving.value = false;
  }
}

async function onFloatExpandedChange(checked) {
  floatSettingsSaving.value = true;
  try {
    await seeUtoken.setFloatExpanded(!!checked);
    floatExpanded.value = !!checked;
  } catch (err) {
    message.error(err?.message || '操作失败');
  } finally {
    floatSettingsSaving.value = false;
  }
}

function openCreate() {
  if (!panelsLoaded.value || !availableProviders.value.length) return;
  formProvider.value = availableProviders.value[0].value;
  createOpen.value = true;
}

async function createPanel() {
  if (!canCreatePanel.value) return;
  creating.value = true;
  try {
    const type = formProvider.value;
    const panel = {
      id: uid(),
      type,
      name: providerLabel(type),
      createdAt: Date.now(),
    };
    const nextPanels = [panel, ...panels.value];
    const saved = await seeUtoken.setSettings({ panels: nextPanels });
    panels.value = Array.isArray(saved?.panels) ? saved.panels : nextPanels;
    createOpen.value = false;
    message.success(`已创建 ${panel.name}`);
    if (type === 'cursor') {
      await seeUtoken.openDashboardDetail();
    }
  } catch (err) {
    message.error(err?.message || '创建失败');
  } finally {
    creating.value = false;
  }
}

function confirmRemove(panel, event) {
  event.stopPropagation();
  modal.confirm({
    title: `删除面板「${panel.name}」？`,
    content: '会同时删除该面板缓存的额度数据。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      const nextPanels = panels.value.filter((p) => p.id !== panel.id);
      const saved = await seeUtoken.setSettings({ panels: nextPanels });
      panels.value = Array.isArray(saved?.panels) ? saved.panels : nextPanels;
      message.success('已删除面板');
    },
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function looksLikeUsageData(data) {
  if (!data || typeof data !== 'object') return false;
  return (
    'quota' in data ||
    'demo' in data ||
    'user' in data ||
    'authSource' in data ||
    'fetchedAt' in data
  );
}

function applyUsage(p) {
  if (!p || typeof p !== 'object') return;
  // 兼容误传成 data 本体
  const payload = p.data !== undefined ? p : { data: p, updatedAt: Date.now() };
  const next = payload.data;
  // 拒绝串台回调（heatmap / navigate 回包）把卡片打回「未连接」
  if (next != null && !looksLikeUsageData(next)) return;
  const prev = usagePayload.value?.data;
  // 已有真实数据时：拒绝演示、空包、以及「不像已连接」的残缺包
  if (isRealCursorUsage(prev)) {
    if (!next || isDemoFlag(next.demo) || !isRealCursorUsage(next)) return;
  }
  if (next && prev && isRealCursorUsage(prev)) {
    const merged = { ...next };
    if (periodTokenCount(merged, 'today') == null && periodTokenCount(prev, 'today') != null) {
      merged.usageTokens = {
        ...(merged.usageTokens || {}),
        today: periodTokenCount(prev, 'today'),
        cycle:
          periodTokenCount(merged, 'cycle') ?? periodTokenCount(prev, 'cycle') ?? merged.usageTokens?.cycle,
      };
      if (!merged.periods && prev.periods) merged.periods = prev.periods;
    } else if (periodTokenCount(merged, 'cycle') == null && periodTokenCount(prev, 'cycle') != null) {
      merged.usageTokens = {
        ...(merged.usageTokens || {}),
        today: periodTokenCount(merged, 'today') ?? periodTokenCount(prev, 'today'),
        cycle: periodTokenCount(prev, 'cycle'),
      };
      if (!merged.periods && prev.periods) merged.periods = prev.periods;
    }
    usagePayload.value = { ...payload, data: merged };
    return;
  }
  usagePayload.value = payload;
}

function hasCursorQuota(p) {
  const raw = p?.data !== undefined ? p?.data : p;
  return isRealCursorUsage(raw);
}

function pullFromPush() {
  const last = seeUtoken.takeLastCard?.();
  if (last) applyUsage(last);
  return last;
}

async function pullUsage() {
  // 1) Python 单向推送缓存（不经过 API 回传，最稳）
  const pushed = pullFromPush();
  if (hasCursorQuota(pushed)) return pushed;
  // 2) 再尝试摘要 API
  try {
    const cached =
      (await seeUtoken.getUsageSummary().catch(() => null)) ||
      (await seeUtoken.getUsage(false).catch(() => null));
    if (cached) applyUsage(cached);
    return cached || pushed;
  } catch (_) {
    return pushed;
  }
}

async function syncCursorUsage() {
  // 立刻吃推送缓存
  let p = await pullUsage();
  if (hasCursorQuota(p)) {
    seeUtoken.refreshUsage().then((r) => applyUsage(r)).catch(() => {});
    return true;
  }
  try {
    const refreshed = await seeUtoken.refreshUsage();
    applyUsage(refreshed);
    if (hasCursorQuota(refreshed)) return true;
  } catch (_) {}
  // 轮询：推送缓存 + API，直到有额度或超时
  for (let i = 0; i < 20; i++) {
    await sleep(300);
    p = await pullUsage();
    if (hasCursorQuota(p)) return true;
  }
  return hasCursorQuota(usagePayload.value);
}

async function goPanel(panel) {
  if (panel.type === 'codex') return seeUtoken.openDashboardDetail('codex');
  if (panel.type !== 'cursor') return;
  const meta = cardMeta(panel);
  if (!meta.connected) {
    try {
      const hint = await seeUtoken.getAuthHint();
      if (hint?.hasSession) {
        message.loading({ content: '正在同步本机 Cursor 用量…', key: 'cursor-sync', duration: 0 });
        const ok = await syncCursorUsage();
        message.destroy('cursor-sync');
        if (!ok) {
          message.warning('已检测到登录，但同步失败，请稍后重试');
          return;
        }
      } else {
        const res = await seeUtoken.startLogin();
        if (!res?.ok) {
          message.error(res?.error || '无法打开登录窗口');
          return;
        }
        message.info('请在弹出窗口中登录 Cursor');
        const started = Date.now();
        while (Date.now() - started < 5 * 60 * 1000) {
          await sleep(1500);
          const st = await seeUtoken.getLoginStatus();
          if (st?.done) break;
          if (!st?.open) break;
        }
        await syncCursorUsage();
      }
    } catch (e) {
      message.destroy('cursor-sync');
      message.error(e?.message || '登录失败');
      return;
    }
  }
  await seeUtoken.openDashboardDetail();
}

let pushPollTimer = null;

onMounted(async () => {
  // 订阅推送（会立刻回放 __seeUtokenLastCard，含 HTML 内联 bootstrap）
  unsub = seeUtoken.onUsageUpdated((p) => applyUsage(p));
  pullFromPush();

  pushPollTimer = window.setInterval(() => {
    if (hasCursorQuota(usagePayload.value)) {
      window.clearInterval(pushPollTimer);
      pushPollTimer = null;
      return;
    }
    pullFromPush();
  }, 350);

  try {
    await loadPanels();
  } catch (_) {}
  await syncCursorUsage();
});

onUnmounted(() => {
  if (unsub) unsub();
  if (pushPollTimer) {
    window.clearInterval(pushPollTimer);
    pushPollTimer = null;
  }
});
</script>

<style scoped>
.quota-home {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 100vh;
  padding: 20px 24px 40px;
  background: var(--sut-bg, #f5f7f9);
  box-sizing: border-box;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
  background: var(--sut-surface, #fff);
  border: 1px solid var(--sut-border, #e7ebf0);
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.toolbar-title {
  font-size: 15px;
  font-weight: 650;
  color: var(--sut-text, #1f2937);
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.settings-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  padding-inline: 0;
  color: var(--sut-secondary, #64748b);
}

.settings-btn:hover {
  color: var(--sut-primary, #1677ff);
}

.settings-modal {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 4px;
}

.settings-section-title {
  margin-bottom: 12px;
  color: var(--sut-secondary, #64748b);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.float-settings-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border: 1px solid var(--sut-border, #e8edf3);
  border-radius: 12px;
  background: var(--sut-inset, #fafbfd);
}

.float-settings-row + .float-settings-row {
  margin-top: 10px;
}

.float-settings-row-stack {
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
}

.glass-style-select {
  width: 100%;
}

.float-settings-label {
  color: var(--sut-text, #0f172a);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
}

.float-settings-desc {
  margin-top: 2px;
  color: var(--sut-muted, #94a3b8);
  font-size: 12px;
  line-height: 1.4;
}

.panel-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.quota-card {
  display: flex;
  flex-direction: column;
  min-height: 228px;
  padding: 18px;
  border: 1px solid var(--sut-border, #e7ebf0);
  border-radius: 16px;
  background: var(--sut-surface, #fff);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}

.quota-card:hover {
  border-color: #91caff;
  box-shadow: 0 8px 24px rgba(22, 119, 255, 0.08);
  transform: translateY(-1px);
}

.card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.card-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.card-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--sut-accent-soft, #e8f3ff);
  color: var(--sut-primary, #1677ff);
  font-size: 18px;
  overflow: hidden;
}

.card-icon.cursor,
.card-icon.codex,
.card-icon.qoder {
  background: transparent;
  border: 0;
  padding: 0;
}

.card-logo {
  width: 36px;
  height: 36px;
  display: block;
  border-radius: 10px;
  object-fit: contain;
}

.card-icon.codex .card-logo,
.card-icon.qoder .card-logo {
  width: 22px;
  height: 22px;
  border-radius: 0;
}

.card-name {
  color: var(--sut-text, #0f172a);
  font-size: 15px;
  font-weight: 650;
  line-height: 1.3;
}

.card-delete {
  color: var(--sut-muted, #94a3b8);
}

.card-mid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 112px 112px;
  column-gap: 18px;
  align-items: center;
  margin-top: 14px;
  min-height: 132px;
}

.card-stats {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 10px;
  min-width: 0;
  min-height: 112px;
  padding: 12px 14px;
  border: 1px solid var(--sut-border, #e8edf3);
  border-radius: 12px;
  background: linear-gradient(180deg, var(--sut-inset, #fafbfd) 0%, var(--sut-inset, #f4f7fb) 100%);
  box-sizing: border-box;
}

.card-stat-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: baseline;
  column-gap: 12px;
}

.card-token-basis {
  color: var(--sut-secondary, #64748b);
  font-size: 11px;
  line-height: 1.3;
}

.card-stat-label {
  color: var(--sut-secondary, #64748b);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.3;
}

.card-stat-v {
  color: var(--sut-text, #0f172a);
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.3;
  white-space: nowrap;
  text-align: right;
}

.card-pool {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  width: 112px;
  justify-self: center;
}

.pool-pct {
  color: var(--sut-text, #0f172a);
  font-size: 16px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.pool-name {
  margin-top: 4px;
  color: var(--sut-secondary, #64748b);
  font-size: 12px;
  font-weight: 600;
}

.card-empty {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 132px;
  text-align: center;
}

.card-remain {
  color: var(--sut-secondary, #334155);
  font-size: 18px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.4;
}

.card-label {
  color: var(--sut-muted, #94a3b8);
  font-size: 12px;
  line-height: 1.5;
}

.card-foot {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: auto;
  padding-top: 16px;
  color: var(--sut-muted, #94a3b8);
  font-size: 12px;
}

.create-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-top: 8px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: var(--sut-secondary, #475569);
  font-size: 13px;
}

.provider-option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.provider-option-icon {
  width: 18px;
  height: 18px;
  display: block;
  border-radius: 4px;
}

.provider-option-fallback {
  font-size: 14px;
  color: var(--sut-secondary, #64748b);
}

.hint {
  margin: 0;
  color: var(--sut-muted, #8b95a5);
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 900px) {
  .panel-grid {
    grid-template-columns: 1fr;
  }
}
</style>
