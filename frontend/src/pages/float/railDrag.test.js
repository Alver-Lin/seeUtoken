import assert from 'node:assert/strict';
import test from 'node:test';
import { createRailDrag } from './railDrag.js';

function fixture() {
  const actions = [];
  let captured = false;
  const target = {
    setPointerCapture(id) { captured = true; actions.push(['capture', id]); },
    hasPointerCapture() { return captured; },
    releasePointerCapture(id) { captured = false; actions.push(['release', id]); },
  };
  const event = (x = 100, y = 200, id = 1) => ({
    button: 0, pointerId: id, screenX: x, screenY: y, currentTarget: target,
  });
  const drag = createRailDrag({
    start: () => actions.push(['start']),
    move: (dx, dy) => actions.push(['move', dx, dy]),
    end: () => actions.push(['end']),
  });
  return { actions, event, drag };
}

test('both clicks of a double click remain targeted at the provider button', () => {
  const { actions, event, drag } = fixture();
  for (let click = 0; click < 2; click++) {
    drag.down(event());
    drag.move(event(101, 201));
    drag.up(event(101, 201));
    assert.equal(drag.moved, false);
    assert.equal(drag.active, false);
  }
  assert.deepEqual(actions, []);
});

test('movement accumulates until threshold, then captures and drags from initial point', () => {
  const { actions, event, drag } = fixture();
  drag.down(event());
  drag.move(event(102, 200));
  assert.deepEqual(actions, []);
  drag.move(event(104, 201));
  drag.move(event(108, 205));
  drag.up(event(108, 205));
  assert.deepEqual(actions, [
    ['capture', 1], ['start'], ['move', 4, 1], ['move', 4, 4], ['release', 1], ['end'],
  ]);
  assert.equal(drag.moved, true);
  drag.down(event());
  assert.equal(drag.moved, false);
});

test('pointer cancellation and lost capture end a drag only once', () => {
  const { actions, event, drag } = fixture();
  drag.down(event());
  drag.move(event(110, 200));
  drag.up(event());
  drag.up(event());
  assert.equal(actions.filter(([name]) => name === 'end').length, 1);
});

test('right clicks and other pointers do not move or end the active drag', () => {
  const { actions, event, drag } = fixture();
  drag.down({ ...event(), button: 2 });
  assert.equal(drag.active, false);
  drag.down(event());
  drag.move(event(130, 200, 2));
  drag.up(event(130, 200, 2));
  assert.deepEqual(actions, []);
  assert.equal(drag.active, true);
});
