/* A slim bar beside the sheet. The page itself stays clear, and this bar moves it. */

import { el } from "./dom.js";


const MIN_THUMB = 44;
const NUDGE = 48;

export function holdPages(scroller) {
  const frame = el("div", { class: "sheet-frame" });
  const bar = el("div", { class: "sheet-bar", attrs: { role: "scrollbar", "aria-orientation": "vertical", "aria-valuemin": "0", "aria-valuemax": "0", "aria-valuenow": "0", "aria-label": "Pages", tabindex: "0" } });
  const thumb = el("span", { class: "sheet-thumb", attrs: { "aria-hidden": "true" } });
  bar.append(thumb);
  if (!scroller.id) scroller.id = "sheet-pages";
  bar.setAttribute("aria-controls", scroller.id);
  frame.append(scroller, bar);
  const state = { frame, bar, thumb, scroller, height: 0, frameId: 0, live: true, drag: null };
  state.onScroll = () => schedule(state);
  state.onPress = (event) => press(state, event);
  state.onKey = (event) => keys(state, event);
  state.onWheel = (event) => wheel(state, event);
  scroller.addEventListener("scroll", state.onScroll, { passive: true });
  bar.addEventListener("pointerdown", state.onPress);
  bar.addEventListener("keydown", state.onKey);
  bar.addEventListener("wheel", state.onWheel, { passive: false });
  state.resize = new ResizeObserver(() => schedule(state));
  state.resize.observe(scroller);
  if (scroller.firstElementChild) state.resize.observe(scroller.firstElementChild);
  schedule(state);
  return { frame, close: () => release(state) };
}

function release(state) {
  state.live = false;
  if (state.frameId) cancelAnimationFrame(state.frameId);
  if (state.drag) state.drag();
  state.scroller.removeEventListener("scroll", state.onScroll);
  state.bar.removeEventListener("pointerdown", state.onPress);
  state.bar.removeEventListener("keydown", state.onKey);
  state.bar.removeEventListener("wheel", state.onWheel);
  state.resize.disconnect();
}

function schedule(state) {
  if (!state.live || state.frameId) return;
  state.frameId = requestAnimationFrame(() => { state.frameId = 0; if (state.live) sync(state); });
}

function sync(state) {
  const span = state.scroller.scrollHeight - state.scroller.clientHeight;
  const can = span > 2 && state.scroller.clientHeight > 0;
  state.frame.classList.toggle("scrolling", can);
  if (!can) return;
  const box = metrics(state, span);
  if (box.track < 1) { schedule(state); return; }
  place(state, box);
  state.bar.setAttribute("aria-valuemax", String(Math.round(box.span)));
  state.bar.setAttribute("aria-valuenow", String(Math.round(state.scroller.scrollTop)));
}

function metrics(state, span) {
  const full = state.scroller.scrollHeight;
  const view = state.scroller.clientHeight;
  const track = state.bar.clientHeight;
  const thumb = Math.min(track, Math.max(MIN_THUMB, Math.round(track * (view / full))));
  return { span, track, thumb, room: Math.max(1, track - thumb) };
}

function place(state, box) {
  const y = (state.scroller.scrollTop / box.span) * box.room;
  if (state.height !== box.thumb) { state.height = box.thumb; state.thumb.style.height = box.thumb + "px"; }
  state.thumb.style.transform = "translate3d(-50%," + y.toFixed(1) + "px,0)";
}

function press(state, event) {
  if (event.button !== 0 || !state.frame.classList.contains("scrolling")) return;
  event.preventDefault();
  if (event.target === state.thumb) hold(state, event);
  else stepTo(state, event);
}

function hold(state, event) {
  const box = metrics(state, state.scroller.scrollHeight - state.scroller.clientHeight);
  const origin = event.clientY;
  const start = state.scroller.scrollTop;
  state.bar.classList.add("holding");
  state.bar.setPointerCapture(event.pointerId);
  const move = (ev) => { if (state.live) state.scroller.scrollTop = clamp(start + ((ev.clientY - origin) / box.room) * box.span, 0, box.span); };
  const end = () => { state.bar.classList.remove("holding"); state.bar.removeEventListener("pointermove", move); state.bar.removeEventListener("pointerup", end); state.bar.removeEventListener("pointercancel", end); state.drag = null; };
  state.drag = end;
  state.bar.addEventListener("pointermove", move);
  state.bar.addEventListener("pointerup", end);
  state.bar.addEventListener("pointercancel", end);
}

function stepTo(state, event) {
  const box = metrics(state, state.scroller.scrollHeight - state.scroller.clientHeight);
  if (box.span <= 0) return;
  const y = event.clientY - state.bar.getBoundingClientRect().top - box.thumb / 2;
  state.scroller.scrollTop = clamp((y / box.room) * box.span, 0, box.span);
}

function keys(state, event) {
  const span = state.scroller.scrollHeight - state.scroller.clientHeight;
  if (span <= 2) return;
  const page = state.scroller.clientHeight;
  let next = state.scroller.scrollTop;
  if (event.key === "ArrowDown") next += NUDGE;
  else if (event.key === "ArrowUp") next -= NUDGE;
  else if (event.key === "PageDown") next += page;
  else if (event.key === "PageUp") next -= page;
  else if (event.key === "Home") next = 0;
  else if (event.key === "End") next = span;
  else return;
  event.preventDefault();
  state.scroller.scrollTop = clamp(next, 0, span);
}

function wheel(state, event) {
  if (!state.frame.classList.contains("scrolling")) return;
  state.scroller.scrollTop += event.deltaY;
  event.preventDefault();
}

function clamp(value, min, max) { return Math.min(max, Math.max(min, value)); }
