export function formatMoney(dollars, digits = 2) {
  const n = Number(dollars) || 0;
  return `$${n.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

export function formatTokens(n) {
  const v = Number(n) || 0;
  if (v >= 100_000_000) {
    const x = v / 100_000_000;
    return `${x >= 10 ? x.toFixed(0) : x.toFixed(1)}亿`;
  }
  if (v >= 10_000) {
    const x = v / 10_000;
    return `${x >= 100 ? x.toFixed(0) : x.toFixed(1)}万`;
  }
  return String(Math.round(v));
}

/** 悬停提示等场景：带千分位的完整 Token 数 */
export function formatTokensExact(n) {
  const v = Math.round(Number(n) || 0);
  return v.toLocaleString('zh-CN');
}

export function formatPercent(p, digits = 0) {
  return `${(Number(p) || 0).toFixed(digits)}%`;
}

export function maskEmail(email) {
  if (!email || !email.includes('@')) return email || '未登录';
  const [name, domain] = email.split('@');
  if (name.length <= 2) return `${name[0]}***@${domain}`;
  return `${name.slice(0, 2)}***${name.slice(-2)}@${domain}`;
}

export function formatDateTime(ts) {
  if (!ts) return '—';
  const d = ts instanceof Date ? ts : new Date(typeof ts === 'string' && /^\d+$/.test(ts) ? Number(ts) : ts);
  if (Number.isNaN(d.getTime())) return '—';
  const y = d.getFullYear();
  const m = d.getMonth() + 1;
  const day = d.getDate();
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${y}年${m}月${day}日 ${hh}:${mm}`;
}

export function formatDateRange(start, end) {
  const fmt = (ts) => {
    if (ts == null || ts === '') return '—';
    const n = typeof ts === 'string' && /^\d+$/.test(ts) ? Number(ts) : ts;
    const d = new Date(n);
    if (Number.isNaN(d.getTime())) return '—';
    return `${d.getMonth() + 1}月${d.getDate()}日`;
  };
  if (!start && !end) return '';
  return `${fmt(start)} – ${fmt(end)}`;
}

export function formatCountdown(resetAt) {
  if (!resetAt) return '—';
  const diff = Math.max(0, new Date(resetAt).getTime() - Date.now());
  const days = Math.floor(diff / 86_400_000);
  const hours = Math.floor((diff % 86_400_000) / 3_600_000);
  return `还剩 ${days} 天 ${hours} 小时`;
}

export function startOfWeek(date = new Date()) {
  const d = new Date(date);
  const day = d.getDay() || 7;
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - day + 1);
  return d;
}

export function kindLabel(kind) {
  if (!kind) return '调用';
  if (kind.includes('INCLUDED')) return '套餐内';
  if (kind.includes('ON_DEMAND') || kind.includes('USAGE_BASED')) return '按量';
  if (kind.includes('ERRORED')) return '失败';
  return '调用';
}

export function formatUpdateTime(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '—';
  return `更新 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
}
