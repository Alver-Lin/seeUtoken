<template>
  <section class="weekly-usage" :aria-label="`近 7 日 Token 用量，${tokenBasisLabel(includeCachedTokens)}`">
    <header class="weekly-head">
      <span class="weekly-month">{{ chart.monthLabel }}</span>
      <span class="weekly-range">近 7 日</span>
    </header>
    <div class="weekly-today">
      <span class="weekly-token-label">Token</span>
      <div class="weekly-value-viewport" :aria-label="dayLabel(selectedDay)" aria-live="polite" aria-atomic="true">
        <AnimatedMetric v-if="selectedDay.tokens != null && !reducedMotion" class="weekly-value" :value="selectedDay.tokens" mode="exact" />
        <span v-else class="weekly-value">{{ selectedDay.tokens == null ? '—' : formatTokensExact(selectedDay.tokens) }}</span>
      </div>
    </div>
    <ol class="weekly-days" @pointerleave="hoveredDate = null">
      <li v-for="day in chart.days" :key="day.date" class="weekly-day" :class="{ 'is-today': day.today, 'is-active': day.date === selectedDay.date, 'is-hovered': day.date === hoveredDate }"
        tabindex="0" :aria-label="dayLabel(day)"
        @pointerenter="onDayEnter(day.date)" @focus="focusedDate = day.date" @blur="focusedDate = null">
        <div class="weekly-bar-slot" aria-hidden="true">
          <span class="weekly-bar" :style="{ height: day.height + '%', minHeight: day.tokens > 0 ? '2px' : '0' }" />
        </div>
        <span class="weekly-weekday" aria-hidden="true">{{ day.weekday }}</span>
        <time class="weekly-date" :datetime="day.date" :aria-current="day.today ? 'date' : undefined">{{ day.day }}</time>
      </li>
    </ol>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';
import AnimatedMetric from './AnimatedMetric.vue';
import { seeUtoken } from '../bridge';
import { weeklyUsage } from '../utils/weeklyUsage';
import { formatTokensExact } from '../utils/format';
import { tokenBasisLabel } from '../utils/tokenAccounting';

const props = defineProps({
  dailyUsage: { type: Array, default: null },
  todayTokens: { type: Number, default: null },
  includeCachedTokens: { type: Boolean, default: false },
});
const now = ref(new Date());
const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
const reducedMotion = ref(motionPreference.matches);
const onMotionChange = event => { reducedMotion.value = event.matches; };
motionPreference.addEventListener('change', onMotionChange);
const chart = computed(() => weeklyUsage(props.dailyUsage, props.todayTokens, now.value));
const hoveredDate = ref(null);
const focusedDate = ref(null);
const selectedDay = computed(() => chart.value.days.find(day => day.date === (hoveredDate.value || focusedDate.value)) || chart.value.days[6]);
function onDayEnter(date) {
  if (hoveredDate.value === date) return;
  hoveredDate.value = date;
  seeUtoken.performHaptic('alignment');
}
let timer;
onMounted(() => { timer = window.setInterval(() => { now.value = new Date(); }, 60000); });
onUnmounted(() => {
  window.clearInterval(timer);
  motionPreference.removeEventListener('change', onMotionChange);
});
function dayLabel(day) {
  return `${day.date} 星期${day.weekday}${day.today ? '（今天）' : ''} · ${day.tokens == null ? '用量待同步' : `${formatTokensExact(day.tokens)} Token`} · ${tokenBasisLabel(props.includeCachedTokens)}`;
}
</script>

<style scoped>
.weekly-usage { min-width: 0; padding: 2px 0; }
.weekly-head { display: flex; align-items: baseline; justify-content: space-between; gap: 6px; margin-bottom: 6px; white-space: nowrap; }
.weekly-month { color: var(--sut-text, #0f172a); font-size: 13px; font-weight: 650; }
.weekly-range { color: var(--sut-muted, #718198); font-size: 10px; letter-spacing: 1px; }
.weekly-today { display: flex; align-items: baseline; gap: 8px; height: 22px; margin-bottom: 8px; color: var(--sut-secondary, #64748b); font-size: 11px; line-height: 22px; }
.weekly-token-label { flex-shrink: 0; }
.weekly-value-viewport { flex: 1; min-width: 0; height: 22px; text-align: right; }
.weekly-value { height: 22px; line-height: 22px; color: var(--sut-text, #0f172a); font-size: 15px; font-weight: 650; font-variant-numeric: tabular-nums; white-space: nowrap; transform-origin: right center; }
.weekly-value.bump { color: var(--sut-text, #0f172a); transform: scale(1.04); }
.weekly-days { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 6px; list-style: none; margin: 0; padding: 0; }
.weekly-day { display: flex; flex-direction: column; align-items: center; min-width: 0; border-radius: 4px; outline-offset: 3px; }
.weekly-day:focus-visible { outline: 2px solid var(--sut-primary, #1677ff); }
.weekly-bar-slot { display: flex; align-items: flex-end; justify-content: center; height: 62px; width: 100%; margin-bottom: 7px; }
.weekly-bar { display: block; width: 100%; max-width: 28px; border-radius: 5px; background: color-mix(in srgb, var(--sut-secondary, #64748b) 28%, transparent); transition: background-color 180ms ease, transform 180ms cubic-bezier(.22, .72, .2, 1); }
.weekly-weekday { color: var(--sut-muted, #718198); font-size: 11px; line-height: 16px; transition: color 180ms ease; }
.weekly-date { display: flex; align-items: center; justify-content: center; width: 20px; height: 20px; margin-top: 3px; color: var(--sut-secondary, #64748b); font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums; border-radius: 50%; transition: color 180ms ease; }
.is-today .weekly-bar { background: #4da7b0; }
.is-active:not(.is-today) .weekly-bar { background: var(--sut-secondary, #64748b); }
.is-hovered .weekly-bar { transform: translateY(-2px); }
.is-active .weekly-weekday { color: var(--sut-text, #0f172a); }
.is-today .weekly-weekday { color: var(--sut-text, #0f172a); }
.is-today .weekly-date { color: var(--sut-elevated, #fff); background: var(--sut-text, #0f172a); }
@media (prefers-reduced-motion: reduce) {
  .weekly-bar, .weekly-weekday, .weekly-date { transition: none; }
  .is-hovered .weekly-bar { transform: none; }
}
</style>
