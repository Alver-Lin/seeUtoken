/**
 * 悬浮窗玻璃轮廓（移植 token-monitor edgeDock/shapes.js 的命令格式）。
 * 同一份命令有两个消费者必须逐像素一致：
 *   - Python 侧把它光栅化成 NSGlassEffectView 的 _setPath: 轮廓
 *   - 前端据此决定何时让 CSS 玻璃退场
 * 坐标为自上而下（与 getBoundingClientRect 一致），Python 侧负责翻转 y。
 */
import { nextTick, onMounted, onUnmounted, watch } from 'vue';
import { seeUtoken } from '../../bridge';

// 四分之一圆角到三次贝塞尔控制点的最佳近似比例（token-monitor ARC）
const ARC = 0.448;

/** 圆角矩形（rail 胶囊 = r 取宽高的上限） */
export function roundedRectCommands(x, y, w, h, r) {
  const rr = Math.max(0, Math.min(r, w / 2, h / 2));
  return [
    ['M', x + rr, y],
    ['L', x + w - rr, y],
    ['C', x + w - rr * ARC, y, x + w, y + rr * ARC, x + w, y + rr],
    ['L', x + w, y + h - rr],
    ['C', x + w, y + h - rr * ARC, x + w - rr * ARC, y + h, x + w - rr, y + h],
    ['L', x + rr, y + h],
    ['C', x + rr * ARC, y + h, x, y + h - rr * ARC, x, y + h - rr],
    ['L', x, y + rr],
    ['C', x, y + rr * ARC, x + rr * ARC, y, x + rr, y],
    ['Z'],
  ];
}

/**
 * 带右指向尾巴的圆角卡片（token-monitor bubbleCommands 的偏移版）。
 * 尾巴尖端收在 rail 内侧 1px：贴边的尖端会被抗锯齿描边切掉一半。
 */
export function popTailCommands({ x, y, width, height, tipX, tailY, neck, radius }) {
  const bw = x + width;
  const tail = Math.max(1, tipX - bw);
  const r = Math.max(0, Math.min(radius, height / 2, width / 2));
  const n = Math.max(0, Math.min(neck, (height - 2 * r) / 2));
  const ty = Math.max(r + n, Math.min(height - r - n, Number(tailY) || height / 2));
  return [
    ['M', x + r, y],
    ['L', bw - r, y],
    ['C', bw - r * ARC, y, bw, y + r * ARC, bw, y + r],
    ['L', bw, y + ty - n],
    ['C', bw, y + ty - n * 0.4, bw + tail * 0.5, y + ty - 1.5, tipX, y + ty],
    ['C', bw + tail * 0.5, y + ty + 1.5, bw, y + ty + n * 0.4, bw, y + ty + n],
    ['L', bw, y + height - r],
    ['C', bw, y + height - r * ARC, bw - r * ARC, y + height, bw - r, y + height],
    ['L', x + r, y + height],
    ['C', x + r * ARC, y + height, x, y + height - r * ARC, x, y + height - r],
    ['L', x, y + r],
    ['C', x, y + r * ARC, x + r * ARC, y, x + r, y],
    ['Z'],
  ];
}

/**
 * 监听悬浮窗几何变化，把 rail / 收起窄条 + pop 卡片的联合轮廓上报给 Python。
 * 所有材质都上报命中区域，供原生贴边控制器判断是否仍在悬停。
 * @param {{ railRef: import('vue').Ref, popRef: import('vue').Ref, hoveredId: import('vue').Ref<string|null>, popTailTop: import('vue').Ref<number>, glassStyle: import('vue').Ref<string>, nativeMaterialTick: import('vue').Ref<number> }} opts
 */
export function useNativeGlassShape({ railRef, popRef, hoveredId, popTailTop, popOffsetY, glassStyle, nativeMaterialTick, dockState, tabRef }) {
  let timer = null;
  let ro = null;
  let lastKey = '';

  const send = () => {
    const collapsed = !!dockState?.value?.collapsed && !dockState?.value?.nativeHandle;
    const left = dockState?.value?.edge === 'left';
    const railEl = collapsed ? tabRef?.value : railRef.value;
    if (!railEl) return;
    const rail = railEl.getBoundingClientRect();
    if (rail.width < 2 || rail.height < 2) return;
    const commands = [];
    const toRect = (rect) => ({ x: rect.left, y: rect.top, width: rect.width, height: rect.height });
    const hitRects = [toRect(rail)];
    const popEl = !collapsed && hoveredId.value ? popRef.value : null;
    if (popEl) {
      const pop = popEl.getBoundingClientRect();
      if (pop.width > 2 && pop.height > 2) {
        hitRects.push(toRect(pop));
        const gapLeft = Math.min(pop.right, rail.right);
        const gapRight = Math.max(pop.left, rail.left);
        if (gapRight > gapLeft) hitRects.push({ x: gapLeft, y: Math.min(pop.top, rail.top), width: gapRight - gapLeft, height: Math.max(pop.bottom, rail.bottom) - Math.min(pop.top, rail.top) });
        const bubble = popTailCommands({
            x: left ? window.innerWidth - pop.right : pop.left,
            y: pop.top,
            width: pop.width,
            height: pop.height,
            tipX: left ? window.innerWidth - rail.right - 1 : Math.max(pop.right, rail.left - 1),
            tailY: popTailTop.value,
            neck: 12,
            radius: 36,
          });
        commands.push(...(left ? bubble.map(([op, ...coords]) => [op, ...coords.map((value, index) => index % 2 === 0 ? window.innerWidth - value : value)]) : bubble));
      }
    }
    commands.push(
      ...roundedRectCommands(rail.left, rail.top, rail.width, rail.height, collapsed ? 3 : rail.width / 2)
    );
    const payload = {
      commands,
      width: window.innerWidth,
      height: window.innerHeight,
      collapsed,
      railRect: toRect(rail),
      hitRects,
    };
    const key = JSON.stringify(payload);
    if (key === lastKey) return;
    lastKey = key;
    seeUtoken.setFloatGlassShape(payload).catch(() => {});
  };

  const schedule = () => {
    nextTick(send);
    if (timer) window.clearTimeout(timer);
    // 等 0.14s 弹窗展开动画结束后再校正一次最终几何
    timer = window.setTimeout(send, 200);
  };

  onMounted(() => {
    ro = new ResizeObserver(() => schedule());
    if (railRef.value) ro.observe(railRef.value);
    window.addEventListener('resize', schedule);
    schedule();
  });

  watch([hoveredId, popTailTop, popOffsetY, glassStyle, nativeMaterialTick, dockState], schedule);

  onUnmounted(() => {
    if (ro) ro.disconnect();
    window.removeEventListener('resize', schedule);
    if (timer) window.clearTimeout(timer);
  });
}
