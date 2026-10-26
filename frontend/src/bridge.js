/** 对接 Python pywebview.api */

const listeners = new Set();

function whenReady() {
  return new Promise((resolve) => {
    if (window.pywebview?.api) {
      resolve(window.pywebview.api);
      return;
    }
    window.addEventListener('pywebviewready', () => resolve(window.pywebview.api), { once: true });
    let n = 0;
    const t = setInterval(() => {
      n += 1;
      if (window.pywebview?.api) {
        clearInterval(t);
        resolve(window.pywebview.api);
      } else if (n > 100) {
        clearInterval(t);
        resolve(null);
      }
    }, 50);
  });
}

async function call(method, ...args) {
  const api = await whenReady();
  if (!api || typeof api[method] !== 'function') {
    throw new Error(`API 不可用: ${method}`);
  }
  return api[method](...args);
}

window.__seeUtokenPush = (payload) => {
  listeners.forEach((cb) => {
    try {
      cb(payload);
    } catch (_) {}
  });
};

export const seeUtoken = {
  getUsage: (force) => call('get_usage', !!force),
  refreshUsage: () => call('refresh_usage_api'),
  getHeatmap: (year) => call('get_heatmap', Number(year)),
  getSettings: () => call('get_settings'),
  setSettings: (settings) => call('set_settings', settings || {}),
  openDashboard: () => call('open_dashboard'),
  openDashboardDetail: () => call('open_dashboard_detail'),
  openPanels: () => call('open_panels'),
  hideDashboard: () => call('hide_dashboard'),
  setFloatExpanded: (expanded) => call('set_float_expanded', !!expanded),
  moveFloatBy: (dx, dy) => call('move_float_by', dx, dy),
  quit: () => call('quit_app'),
  onUsageUpdated: (cb) => {
    listeners.add(cb);
    return () => listeners.delete(cb);
  },
};
