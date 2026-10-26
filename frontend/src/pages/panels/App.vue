<template>
  <div class="quota-home">
    <div class="toolbar">
      <div>
        <div class="toolbar-title">模型额度</div>
      </div>
      <a-button type="primary" @click="openCreate">
        <template #icon><PlusOutlined /></template>
        新建额度面板
      </a-button>
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
          <div class="card-stats">
            <div class="card-remain">{{ cardMeta(panel).remainText }}</div>
            <div class="card-label">
              {{ cardMeta(panel).connected ? "剩余额度" : "待连接" }}
            </div>
          </div>
          <div v-if="cardMeta(panel).connected" class="card-ring">
            <svg viewBox="0 0 72 72" aria-hidden="true">
              <g transform="rotate(-90 36 36)">
                <circle class="ring-track" cx="36" cy="36" r="28" />
                <circle
                  class="ring-value"
                  cx="36"
                  cy="36"
                  r="28"
                  pathLength="100"
                  :stroke="cardMeta(panel).remainColor"
                  :stroke-dasharray="ringDash(cardMeta(panel).remainRatio)"
                />
              </g>
            </svg>
            <span class="ring-pct">{{ cardMeta(panel).percentText }}</span>
          </div>
        </div>

        <div class="card-foot">
          <span>{{ cardMeta(panel).planText }}</span>
          <span v-if="cardMeta(panel).updatedText">更新 {{ cardMeta(panel).updatedText }}</span>
        </div>
      </article>
    </section>

    <a-modal
      v-model:open="createOpen"
      title="新建额度面板"
      ok-text="创建并进入"
      cancel-text="取消"
      :confirm-loading="creating"
      @ok="createPanel"
    >
      <div class="create-form">
        <label class="field">
          <span>服务商</span>
          <a-select v-model:value="formProvider" style="width: 100%">
            <a-select-option
              v-for="item in QUOTA_PROVIDERS"
              :key="item.value"
              :value="item.value"
            >
              <span class="provider-option">
                <img
                  v-if="providerIcon(item.value)"
                  class="provider-option-icon"
                  :src="providerIcon(item.value)"
                  alt=""
                />
                <ThunderboltOutlined v-else class="provider-option-fallback" />
                {{ item.label }}
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
import { PlusOutlined, ThunderboltOutlined, DeleteOutlined } from '@ant-design/icons-vue';
import cursorLogo from '../../assets/brand/cursor-logo.svg';
import codexLogo from '../../assets/brand/codex-logo.svg';
import qoderLogo from '../../assets/brand/qoder-logo.svg';
import { seeUtoken } from '../../bridge';
import { formatMoney } from '../../utils/format';

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
const usagePayload = ref(null);
const createOpen = ref(false);
const creating = ref(false);
const formProvider = ref('cursor');
let unsub = null;

const createHint = computed(() => {
  if (formProvider.value === 'cursor') {
    return '创建后进入面板，可登录 Cursor 并实时同步额度。';
  }
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

function ringDash(ratio) {
  if (ratio == null) return '0 100';
  const value = Math.max(0, Math.min(1, ratio)) * 100;
  return `${value} 100`;
}

function cardMeta(panel) {
  if (panel.type !== 'cursor') {
    return {
      remainText: '未接入',
      planText: '额度接入即将支持',
      updatedText: '',
      connected: false,
      remainRatio: null,
      remainColor: '#e6ebf2',
      percentText: '',
    };
  }

  const data = usagePayload.value?.data;
  if (!data?.quota) {
    return {
      remainText: '未连接',
      planText: '进入面板后登录并刷新',
      updatedText: '',
      connected: false,
      remainRatio: null,
      remainColor: '#e6ebf2',
      percentText: '',
    };
  }

  const remain = Math.max(Number(data.quota.remaining) || 0, 0);
  const used = Math.max(Number(data.quota.used) || 0, 0);
  const total =
    data.quota.total != null && Number(data.quota.total) > 0
      ? Number(data.quota.total)
      : remain + used;
  const remainRatio = total > 0 ? remain / total : 0;
  const remainColor =
    remainRatio <= 0 ? '#ff4d4f' : remainRatio < 0.2 ? '#fa8c16' : '#1677ff';
  const ts = usagePayload.value?.updatedAt || data.fetchedAt;
  const updatedText = ts
    ? new Date(ts).toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : '';

  return {
    remainText: formatMoney(remain),
    planText: `总量 ${formatMoney(total)}`,
    updatedText,
    connected: true,
    remainRatio,
    remainColor,
    percentText: `${Math.round(remainRatio * 100)}%`,
  };
}

async function persist() {
  await seeUtoken.setSettings({ panels: panels.value });
}

async function loadPanels() {
  const s = await seeUtoken.getSettings();
  if (Array.isArray(s?.panels) && s.panels.length) {
    panels.value = s.panels.map((p) => ({
      ...p,
      type: p.type || p.provider || 'cursor',
    }));
  } else {
    panels.value = [...DEFAULT_PANELS];
    await persist();
  }
}

function openCreate() {
  formProvider.value = 'cursor';
  createOpen.value = true;
}

async function createPanel() {
  creating.value = true;
  try {
    const type = formProvider.value;
    const panel = {
      id: uid(),
      type,
      name: providerLabel(type),
      createdAt: Date.now(),
    };
    panels.value = [panel, ...panels.value];
    await persist();
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
  Modal.confirm({
    title: `删除面板「${panel.name}」？`,
    content: '会同时删除该面板缓存的额度数据。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      panels.value = panels.value.filter((p) => p.id !== panel.id);
      await persist();
      message.success('已删除面板');
    },
  });
}

async function goPanel(panel) {
  if (panel.type !== 'cursor') return;
  await seeUtoken.openDashboardDetail();
}

onMounted(async () => {
  await loadPanels();
  try {
    usagePayload.value = await seeUtoken.getUsage(true);
  } catch (_) {}
  unsub = seeUtoken.onUsageUpdated((p) => {
    usagePayload.value = p;
  });
});

onUnmounted(() => {
  if (unsub) unsub();
});
</script>

<style scoped>
.quota-home {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 100vh;
  padding: 20px 24px 40px;
  background: #f5f7f9;
  box-sizing: border-box;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
  background: #fff;
  border: 1px solid #e7ebf0;
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.toolbar-title {
  font-size: 15px;
  font-weight: 650;
  color: #1f2937;
}

.panel-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.quota-card {
  display: flex;
  flex-direction: column;
  min-height: 210px;
  padding: 18px;
  border: 1px solid #e7ebf0;
  border-radius: 16px;
  background: #fff;
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
  background: #e8f3ff;
  color: #1677ff;
  font-size: 18px;
  overflow: hidden;
}

.card-icon.cursor {
  background: transparent;
  padding: 0;
}

.card-icon.codex,
.card-icon.qoder {
  background: #f8fafc;
  border: 1px solid #e7ebf0;
  padding: 6px;
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
  color: #0f172a;
  font-size: 15px;
  font-weight: 650;
  line-height: 1.3;
}

.card-delete {
  color: #94a3b8;
}

.card-mid {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 16px;
  margin-top: 10px;
  min-height: 118px;
  padding-right: 20px;
}

.card-stats {
  min-width: 0;
  flex: 1 1 auto;
}

.card-remain {
  color: #0f172a;
  font-size: 28px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.15;
}

.card-label {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
}

.card-ring {
  position: relative;
  width: 118px;
  height: 118px;
  flex: 0 0 118px;
  margin-right: 4px;
}

.card-ring svg {
  display: block;
  width: 118px;
  height: 118px;
}

.ring-track,
.ring-value {
  fill: none;
  stroke-width: 10;
}

.ring-track {
  stroke: #eef2f7;
}

.ring-value {
  stroke-linecap: round;
  transition: stroke-dasharray 0.25s ease, stroke 0.25s ease;
}

.ring-pct {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0f172a;
  font-size: 18px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  pointer-events: none;
}

.card-foot {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: auto;
  padding-top: 16px;
  color: #94a3b8;
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
  color: #475569;
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
  color: #64748b;
}

.hint {
  margin: 0;
  color: #8b95a5;
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 900px) {
  .panel-grid {
    grid-template-columns: 1fr;
  }
}
</style>
