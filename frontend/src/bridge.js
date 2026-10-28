/** 对接 Python pywebview.api */

const listeners = new Set();
const heatmapListeners = new Set();

const API_PROBE_METHODS = [
  'get_settings',
  'get_usage',
  'refresh_usage_api',
  'get_usage_summary',
];

function isApiPopulated(api) {
  if (!api || typeof api !== 'object') return false;
  return API_PROBE_METHODS.some((name) => typeof api[name] === 'function');
}

function whenReady() {
  return new Promise((resolve) => {
    const finish = () => {
      const api = window.pywebview?.api;
      resolve(isApiPopulated(api) ? api : api || null);
    };
    if (isApiPopulated(window.pywebview?.api)) {
      resolve(window.pywebview.api);
      return;
    }
    window.addEventListener('pywebviewready', finish, { once: true });
    let n = 0;
    const t = setInterval(() => {
      n += 1;
      if (isApiPopulated(window.pywebview?.api)) {
        clearInterval(t);
        resolve(window.pywebview.api);
      } else if (n > 200) {
        clearInterval(t);
        finish();
      }
    }, 50);
  });
}

function pickApiFn(api, names) {
  for (const name of names) {
    if (typeof api[name] === 'function') return api[name];
  }
  return null;
}

async function call(method, ...args) {
  const api = await whenReady();
  if (!api || typeof api[method] !== 'function') {
    throw new Error(`API 不可用: ${method}`);
  }
  return api[method](...args);
}

async function triggerUsageRefresh() {
  const api = await whenReady();
  if (!api) {
    throw new Error('API 不可用: refresh');
  }
  const refreshFn = pickApiFn(api, [
    'refresh_usage_api',
    'request_refresh',
    'refresh_usage',
    'refreshUsageApi',
    'requestRefresh',
  ]);
  if (refreshFn) {
    return refreshFn.call(api);
  }
  // 这些读接口也会触发 Python 侧后台 refresh_usage_background
  const getUsage = pickApiFn(api, ['get_usage', 'getUsage']);
  if (getUsage) {
    await getUsage.call(api, true);
    return { ok: true, kind: 'ack' };
  }
  const getDetail = pickApiFn(api, ['get_usage_detail', 'getUsageDetail']);
  if (getDetail) {
    await getDetail.call(api);
    return { ok: true, kind: 'ack' };
  }
  const getSummary = pickApiFn(api, ['get_usage_summary', 'getUsageSummary']);
  if (getSummary) {
    await getSummary.call(api);
    return { ok: true, kind: 'ack' };
  }
  throw new Error('API 不可用: refresh');
}

window.__seeUtokenPush = (payload) => {
  window.__seeUtokenLastCard = payload;
  listeners.forEach((cb) => {
    try {
      cb(payload);
    } catch (_) {}
  });
};

window.__seeUtokenDetailPush = (payload) => {
  window.__seeUtokenLastDetail = payload;
  listeners.forEach((cb) => {
    try {
      cb(payload);
    } catch (_) {}
  });
};

window.__seeUtokenHeatmapPush = (payload) => {
  window.__seeUtokenLastHeatmap = payload;
  heatmapListeners.forEach((cb) => {
    try {
      cb(payload);
    } catch (_) {}
  });
};

export const seeUtoken = {
  getUsage: (force) => call('get_usage', !!force),
  getUsageDetail: () => call('get_usage_detail'),
  /** 外层面板：只拉额度摘要，避免大 JSON 把 pywebview 回调弄丢 */
  getUsageSummary: () => call('get_usage_summary'),
  getUsageTokens: () => call('get_usage_tokens'),
  getCursorActivity: () => call('get_cursor_activity'),
  getCodexActivity: async () => {
    if (window.location.hostname === '127.0.0.1') {
      const response = await fetch('/api/codex-activity', { signal: AbortSignal.timeout(4000) });
      if (!response.ok) throw new Error('Codex 运行状态读取失败');
      return response.json();
    }
    return call('get_codex_activity');
  },
  getCodexUsage: async (summary = false, year = null, refresh = false) => {
    // HTTP avoids pywebview's large-result and multiple-window callback limits.
    if (window.location.hostname === '127.0.0.1') {
      const query = new URLSearchParams({ summary: summary ? '1' : '0', refresh: refresh ? '1' : '0' });
      if (year != null) query.set('year', String(year));
      const response = await fetch(`/api/codex-usage?${query}`, { signal: AbortSignal.timeout(15000) });
      if (!response.ok) throw new Error('Codex 数据读取失败');
      return response.json();
    }
    return call('get_codex_usage', summary, year, refresh);
  },
  refreshUsage: () => triggerUsageRefresh(),
  getHeatmap: (year) => call('get_heatmap', Number(year)),
  getSettings: () => call('get_settings'),
  setSettings: (settings) => call('set_settings', settings || {}),
  getNativeMaterialState: () => call('get_native_material_state'),
  /** 上报悬浮窗轮廓（rail 胶囊 + pop 卡片 + 尾巴），驱动 macOS 异形 Liquid Glass */
  setFloatGlassShape: (payload) => call('set_float_glass_shape', payload || {}),
  // 导航会换页，不要卡住 await；后端已延迟 load_url
  openDashboard: () => {
    call('open_dashboard').catch(() => {});
    return Promise.resolve(true);
  },
  openDashboardDetail: (provider = 'cursor') => {
    call('open_dashboard_detail', provider).catch(() => {});
    return Promise.resolve(true);
  },
  openPanels: () => {
    call('open_panels').catch(() => {});
    return Promise.resolve(true);
  },
  hideDashboard: () => call('hide_dashboard'),
  startLogin: () => call('start_login'),
  getLoginStatus: () => call('get_login_status'),
  getAuthHint: () => call('get_auth_hint'),
  setFloatExpanded: (expanded) => call('set_float_expanded', !!expanded),
  moveFloatBy: (dx, dy) => call('move_float_by', dx, dy),
  setFloatDragging: (dragging) => call('set_float_dragging', !!dragging),
  revealFloatDock: () => call('reveal_float_dock'),
  /** macOS 触控板触觉反馈；非 Mac 或无 AppKit 时静默失败 */
  performHaptic: (kind = 'hover') => {
    const api = window.pywebview?.api;
    if (typeof api?.perform_haptic === 'function') {
      try {
        api.perform_haptic(kind).catch(() => {});
      } catch (_) {}
      return Promise.resolve(true);
    }
    call('perform_haptic', kind).catch(() => {});
    return Promise.resolve(true);
  },
  quit: () => call('quit_app'),
  /** 取 Python 启动/刷新时已经推过来的额度摘要（不依赖 API 回传） */
  takeLastCard: () => window.__seeUtokenLastCard || null,
  takeLastDetail: () => window.__seeUtokenLastDetail || null,
  onUsageUpdated: (cb) => {
    listeners.add(cb);
    // 详情优先，避免只用 card 把明细清空
    const detail = window.__seeUtokenLastDetail;
    const card = window.__seeUtokenLastCard;
    if (detail) {
      try {
        cb(detail);
      } catch (_) {}
    } else if (card) {
      try {
        cb(card);
      } catch (_) {}
    }
    return () => listeners.delete(cb);
  },
  onHeatmapUpdated: (cb) => {
    heatmapListeners.add(cb);
    if (window.__seeUtokenLastHeatmap) {
      try {
        cb(window.__seeUtokenLastHeatmap);
      } catch (_) {}
    }
    return () => heatmapListeners.delete(cb);
  },
};
