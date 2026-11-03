export function isCursorAuthError(error) {
  return error?.code === 'NO_SESSION' || error?.code === 'AUTH_EXPIRED';
}

// Missing account/usage data must never look like a full allowance.
export function cursorQuotaState(data, authRequired = false) {
  const connected = !!(
    !authRequired && data && !data.demo &&
    (data.user?.email || ['cursor-db', 'manual'].includes(data.authSource))
  );
  const quota = data?.quota || {};
  const limits = data?.limits || {};
  function remaining(value) {
    if (!connected || value == null || value === '' || !Number.isFinite(Number(value))) return 0;
    return 100 - Math.min(100, Math.max(0, Number(value)));
  }
  const cursorRemainingPercent = remaining(limits.cursorModelsPercent ?? quota.cursorModelsPercent ?? quota.autoPercent);
  const otherRemainingPercent = remaining(limits.otherModelsPercent ?? quota.otherModelsPercent ?? quota.apiPercent);
  return {
    connected,
    cursorRemainingPercent,
    otherRemainingPercent,
    // Ring renderers take the used portion; 100 hides the remaining arc at 0%.
    cursorUsedPercent: 100 - cursorRemainingPercent,
    otherUsedPercent: 100 - otherRemainingPercent,
  };
}
