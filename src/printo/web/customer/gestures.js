/* Pinch, pan, and a horizontal flick. Only the flick changes which photo is open. */

export function trackImage(stage, image, hooks) {
  const state = { scale: 1, x: 0, y: 0, pointers: new Map(), pinch: null, drag: null, lastTap: 0 };
  const onDown = (event) => down(event, stage, image, state);
  const onMove = (event) => move(event, stage, image, state);
  const onUp = (event) => up(event, stage, image, state, hooks);
  const onWheel = (event) => wheel(event, stage, image, state);
  stage.addEventListener("pointerdown", onDown);
  stage.addEventListener("pointermove", onMove);
  stage.addEventListener("pointerup", onUp);
  stage.addEventListener("pointercancel", onUp);
  stage.addEventListener("wheel", onWheel, { passive: false });
  image.addEventListener("dragstart", (event) => event.preventDefault());
  return () => {
    stage.removeEventListener("pointerdown", onDown);
    stage.removeEventListener("pointermove", onMove);
    stage.removeEventListener("pointerup", onUp);
    stage.removeEventListener("pointercancel", onUp);
    stage.removeEventListener("wheel", onWheel);
  };
}

function down(event, stage, image, state) {
  stage.setPointerCapture?.(event.pointerId);
  state.pointers.set(event.pointerId, point(event));
  if (state.pointers.size === 2) { state.pinch = pinchOf(state); state.drag = null; return; }
  state.drag = { x: state.x, y: state.y, px: event.clientX, py: event.clientY, t: performance.now() };
  const now = performance.now();
  if (now - state.lastTap < 280 && state.pointers.size === 1) toggle(stage, image, state);
  state.lastTap = now;
}

function move(event, stage, image, state) {
  if (!state.pointers.has(event.pointerId)) return;
  state.pointers.set(event.pointerId, point(event));
  if (state.pointers.size >= 2 && state.pinch) {
    const next = pinchOf(state);
    state.scale = clamp(state.pinch.scale * (next.distance / state.pinch.distance), 1, 4);
    apply(image, state);
    clampPan(stage, image, state);
    return;
  }
  if (!state.drag || state.scale <= 1) return;
  state.x = state.drag.x + (event.clientX - state.drag.px);
  state.y = state.drag.y + (event.clientY - state.drag.py);
  clampPan(stage, image, state);
  apply(image, state);
}

function up(event, stage, image, state, hooks) {
  const start = state.drag;
  state.pointers.delete(event.pointerId);
  if (state.pointers.size < 2) state.pinch = null;
  if (state.pointers.size === 0 && start && state.scale <= 1.02) {
    const dx = event.clientX - start.px;
    const dy = event.clientY - start.py;
    const quick = performance.now() - start.t < 420;
    if (quick && Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy) * 1.2) hooks.onSwipe(dx < 0 ? 1 : -1);
  }
  if (state.scale < 1.05) reset(image, state);
  state.drag = null;
}

function wheel(event, stage, image, state) {
  event.preventDefault();
  state.scale = clamp(state.scale * (event.deltaY < 0 ? 1.08 : 0.92), 1, 4);
  if (state.scale === 1) reset(image, state);
  else { clampPan(stage, image, state); apply(image, state); }
}

function toggle(stage, image, state) {
  if (state.scale > 1) reset(image, state);
  else { state.scale = 2.4; clampPan(stage, image, state); apply(image, state); }
}

function pinchOf(state) {
  const [a, b] = [...state.pointers.values()];
  return { distance: Math.max(1, Math.hypot(a.x - b.x, a.y - b.y)), scale: state.scale };
}

function clampPan(stage, image, state) {
  const roomX = Math.max(0, (image.clientWidth * state.scale - stage.clientWidth) / 2);
  const roomY = Math.max(0, (image.clientHeight * state.scale - stage.clientHeight) / 2);
  state.x = clamp(state.x, -roomX, roomX);
  state.y = clamp(state.y, -roomY, roomY);
}

function reset(image, state) {
  state.scale = 1;
  state.x = 0;
  state.y = 0;
  apply(image, state);
}

function apply(image, state) {
  image.style.transform = `translate(${state.x}px, ${state.y}px) scale(${state.scale})`;
}

function point(event) {
  return { x: event.clientX, y: event.clientY };
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
