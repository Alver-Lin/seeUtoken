// Preserve clicks on provider buttons; capture only an actual drag.
export function createRailDrag({ start, move, end }) {
  let press = null;
  let moved = false;

  return {
    get moved() { return moved; },
    get active() { return !!press; },
    down(event) {
      if (event.button !== 0 || press) return;
      moved = false;
      press = { x: event.screenX, y: event.screenY, id: event.pointerId, target: event.currentTarget };
    },
    move(event) {
      if (!press || event.pointerId !== press.id) return;
      const dx = event.screenX - press.x;
      const dy = event.screenY - press.y;
      if (!moved) {
        if (Math.abs(dx) + Math.abs(dy) <= 3) return;
        moved = true;
        press.target.setPointerCapture?.(press.id);
        start();
      }
      move(dx, dy);
      press.x = event.screenX;
      press.y = event.screenY;
    },
    up(event) {
      if (!press || event.pointerId !== press.id) return;
      const { target, id } = press;
      press = null;
      if (target.hasPointerCapture?.(id)) target.releasePointerCapture(id);
      if (moved) end();
    },
  };
}
