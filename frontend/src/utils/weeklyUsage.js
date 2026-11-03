const weekdays = ['日', '一', '二', '三', '四', '五', '六'];

export function localDateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function tokenValue(value) {
  return value != null && value !== '' && Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : null;
}

export function weeklyUsage(dailyUsage, todayTokens = null, now = new Date()) {
  const byDate = new Map((dailyUsage || []).map(day => [day.date, tokenValue(day.tokens)]));
  const today = localDateKey(now);
  const currentTokens = tokenValue(todayTokens);
  if (currentTokens != null) byDate.set(today, currentTokens);
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(now);
    date.setHours(12, 0, 0, 0);
    date.setDate(date.getDate() - (6 - index));
    const key = localDateKey(date);
    return { date: key, day: date.getDate(), month: date.getMonth(), weekday: weekdays[date.getDay()],
      today: key === today, tokens: byDate.get(key) ?? null };
  });
  const peak = Math.max(0, ...days.map(day => day.tokens || 0));
  return {
    monthLabel: days[0].month === days[6].month ? `${days[6].month + 1}月` : `${days[0].month + 1}月-${days[6].month + 1}月`,
    days: days.map(day => ({ ...day, height: peak > 0 ? (day.tokens || 0) / peak * 100 : 0 })),
  };
}
