import { onMounted, onUnmounted, ref } from 'vue';
import { seeUtoken } from '../bridge';
import { formatPercent } from './format';

export const CODEX_COLORS = ['#10a37f', '#1677ff'];
export function codexPlanLabel(plan, syncing = false) {
  const value = String(plan || '').trim();
  if (!value) return syncing ? '同步中…' : '套餐未知';
  return value.charAt(0).toUpperCase() + value.slice(1);
}
export function quotaText(window) {
  return window?.remainingPercent == null ? '—' : formatPercent(window.remainingPercent);
}
export function quotaSegments(window, index = 0, track = '#e6ebf2') {
  if (window?.remainingPercent == null) return [{ value: 1, color: track }];
  const remaining = window.remainingPercent;
  const color = remaining < 10 ? '#ff4d4f' : remaining < 20 ? '#fa8c16' : CODEX_COLORS[index % 2];
  return [{ value: remaining, color }, { value: 100 - remaining, color: track }];
}

export function useCodexUsage(summary = true) {
  const data = ref(null);
  const loading = ref(false);
  const error = ref('');
  const year = ref(new Date().getFullYear());
  let timer = null;
  let stopped = false;
  let pending = null;
  let unsubscribe = null;
  async function refresh(force = false) {
    if (pending) return pending;
    loading.value = true;
    pending = (async () => {
      try {
        const payload = await seeUtoken.getCodexUsage(summary, year.value, force);
        if (payload?.data?.provider !== 'codex') throw new Error('Codex 数据暂未就绪');
        data.value = payload.data;
        error.value = '';
        return data.value;
      } catch (e) {
        error.value = e?.message || 'Codex 同步失败';
      } finally {
        loading.value = false;
        pending = null;
      }
    })();
    return pending;
  }
  async function poll() {
    await refresh();
    if (!stopped) timer = window.setTimeout(poll, data.value?.syncing ? 2000 : 15000);
  }
  onMounted(() => {
    unsubscribe = seeUtoken.onUsageUpdated(payload => {
      if (typeof payload?.data?.includeCachedTokens === 'boolean' &&
          payload.data.includeCachedTokens !== data.value?.includeCachedTokens) refresh();
    });
    poll();
  });
  onUnmounted(() => {
    stopped = true;
    window.clearTimeout(timer);
    unsubscribe?.();
  });
  return { data, loading, error, refresh, year };
}
