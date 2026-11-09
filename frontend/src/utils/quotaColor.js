/** Remaining-quota ring colors (shared by Cursor / Codex / float). */
export const QUOTA_REMAIN_COLORS = {
  full: '#10a37f', // 90%–100%
  high: '#1677ff', // 50%–89%
  mid: '#fa8c16', // 10%–49%
  low: '#ff4d4f', // <10%
};

/**
 * Color for a remaining-percent ring.
 * Uses the same rounded value users see in labels.
 */
export function remainingQuotaColor(remainingPercent) {
  const n = Number(remainingPercent);
  const remain = Math.round(Math.max(0, Math.min(100, Number.isFinite(n) ? n : 0)));
  if (remain >= 90) return QUOTA_REMAIN_COLORS.full;
  if (remain >= 50) return QUOTA_REMAIN_COLORS.high;
  if (remain >= 10) return QUOTA_REMAIN_COLORS.mid;
  return QUOTA_REMAIN_COLORS.low;
}
