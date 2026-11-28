/* The sheet on the desk. Each page is a picture saved when the file was prepared.
   Turning a page, or laying the next one beside it, only moves those pictures.
   The file is not opened here. A picture that scrolls far away leaves the screen,
   and comes back from the browser's own cache. */

import { holdPages } from "./bar.js";
import { el } from "./dom.js";
import { clampFit, sizeControl } from "./fit.js";
import { landscapePairs } from "./landscape.js";
import { loadPicture, pictureUrl, placePicture, releasePicture } from "./pictures.js";
import { createRotateDock, flickIcon, paintPairSlots, syncRotateDock } from "./rotate.js";

const NEAR = 480;

let live = null;

export function closeSheets() {
  if (!live) return;
  const view = live;
  live = null;
  shutdown(view);
}

export function showSheets(slot, id, copy) {
  closeSheets();
  const preview = copy.preview || {};
  const view = {
    id, open: true, mark: 1, observer: null, resize: null, hold: null, root: null,
    fit: clampFit(copy.fit), onFit: copy.onFit || null, caption: copy.caption, fail: copy.fail,
    pages: copy.pages ? copy.pages.slice() : null, pool: new Map(), stack: null, scroller: null, frame: null,
    stage: null, dock: null, shown: null, gen: 0, wait: null, follow: 0, poll: 0, timer: 0,
    running: false, again: false,
    pageCount: Math.max(1, copy.pageCount || preview.total || 1),
    revision: preview.revision || "", ready: Number(preview.ready) || 0,
    rotations: copy.rotations ? { ...copy.rotations } : {},
    pair: copy.pair || null,
    canRotate: Boolean(copy.canRotate),
    busyRotate: Boolean(copy.busyRotate),
    selectedPage: copy.selectedPage ?? null,
    selectedSlot: copy.selectedSlot ?? null,
    onSelectPage: copy.onSelectPage || null,
    onSelectSlot: copy.onSelectSlot || null,
    onClearSelection: copy.onClearSelection || null,
    onRotate: copy.onRotate || null,
    landscape: Boolean(copy.landscape),
    onLandscape: copy.onLandscape || null,
  };
  live = view;
  place(view, slot);
  if (view.ready < view.pageCount) follow(view);
}

/* Which pages will print. Called again as the choice changes; nothing is fetched again. */
export function focusSheets(pages) {
  if (!live || !pages || !pages.length) return;
  live.pages = pages.slice();
  if (!live.stack) return;
  if (live.timer) clearTimeout(live.timer);
  live.timer = setTimeout(() => { if (!live || !live.open) return; live.timer = 0; kick(live); }, 80);
}

export function updateSheetsState(next) {
  if (!live || !live.open) return;
  if ("pair" in next) live.pair = next.pair;
  if ("canRotate" in next) live.canRotate = Boolean(next.canRotate);
  if ("busyRotate" in next) live.busyRotate = Boolean(next.busyRotate);
  if ("selectedPage" in next) live.selectedPage = next.selectedPage;
  if ("selectedSlot" in next) live.selectedSlot = next.selectedSlot;
  syncSelection(live);
}

/* The pictures already on screen are laid into the new shape. A missing half stays blank. */
export function setLandscapeMode(on) {
  if (!live || !live.open) return;
  live.landscape = Boolean(on);
  live.mark += 1;
  dropVeil(live);
  applyLandscapeStage(live);
  if (!live.stack) { syncSelection(live); return; }
  const numbers = wanted(live);
  live.shown = keyOf(numbers);
  mount(live, numbers);
  drawVisible(live, live.scroller, live.stack);
  syncSelection(live);
}

export function rotateSheetsInPlace(rotations, targetPages) {
  if (!live || !live.open || !live.stack) return;
  live.rotations = { ...rotations };
  const targets = targetPages && targetPages.length ? new Set(targetPages) : null;
  for (const sheet of live.pool.values()) {
    const num = Number(sheet.dataset.page);
    const mate = Number(sheet.dataset.mate) || 0;
    if (targets && !targets.has(num) && !(mate && targets.has(mate))) continue;
    placeSheet(live, sheet);
  }
}

/* A photo or a Citizenship sheet was rebuilt. Swap in the new picture when it is here. */
export function adoptPreview(status) {
  if (!live || !live.open || !status) return;
  applyStatus(live, status);
  if (live.ready < live.pageCount) follow(live);
}

export function pulseRotateButton() {
  if (!live || !live.dock) return;
  flickIcon(live.dock.querySelector(".rotate-btn"));
}

function shutdown(view) {
  view.open = false;
  view.gen += 1;
  view.follow += 1;
  if (view.timer) clearTimeout(view.timer);
  if (view.poll) clearTimeout(view.poll);
  view.wait?.remove();
  view.wait = null;
  view.hold?.close();
  view.observer?.disconnect();
  view.resize?.disconnect();
  if (view.pool) for (const sheet of view.pool.values()) releaseSheet(sheet);
  view.pool = null;
}

function place(view, slot) {
  if (!current(view, slot)) return;
  const scroller = el("div", { class: "sheet-page", attrs: { role: "region", "aria-label": "Pages" } });
  const stack = el("div", { class: "sheet-stack" });
  scroller.append(stack);
  if (!current(view, slot)) return;
  const held = holdPages(scroller);
  const stage = el("div", { class: "sheet-stage" });
  const dock = createRotateDock({
    onRotate: () => view.onRotate?.(),
    onClear: () => view.onClearSelection?.(),
    onLandscape: () => view.onLandscape?.(),
  });
  const wait = el("div", { class: "preview-wait", attrs: { hidden: "hidden", role: "status" } });
  wait.append(el("span", { class: "spin", attrs: { "aria-hidden": "true" } }), el("p", { text: "Preparing preview…" }));
  held.frame.insertBefore(stage, scroller);
  stage.append(scroller, wait);
  const preview = column(held.frame, dock, view);
  if (!current(view, slot)) { held.close(); return; }
  view.hold = held;
  view.root = preview;
  view.frame = held.frame;
  view.stage = stage;
  view.dock = dock;
  view.wait = wait;
  view.scroller = scroller;
  view.stack = stack;
  slot.replaceChildren(preview);
  applyLandscapeStage(view);
  matchPaper(view, scroller);
  if (!view.open) return;
  listen(view, scroller, stack);
  const pages = wanted(view);
  mount(view, pages);
  view.shown = keyOf(pages);
  paintWait(view);
  syncSelection(view);
  requestAnimationFrame(() => { if (view.open) drawVisible(view, scroller, stack); });
}

function column(frame, dock, view) {
  const preview = el("div", { class: "preview" });
  preview.append(dock, frame);
  if (view.onFit) preview.append(sizeControl(view.fit, (exact, shown) => onSize(view, exact, shown)));
  if (view.caption) preview.append(el("p", { class: "caption", text: view.caption }));
  applyScale(preview, view.fit);
  return preview;
}

function onSize(view, exact, shown) {
  view.fit = shown;
  applyScale(view.root, exact);
  view.onFit?.(shown);
}

/* Scale the already-drawn page. The picture is not fetched again while the slider moves. */
function matchPaper(view, scroller) {
  const width = scroller.clientWidth;
  if (view.root && width) view.root.style.setProperty("--paper", width + "px");
}

function applyScale(node, fit) {
  if (!node) return;
  if (Math.abs(fit - 100) < 0.05) { node.classList.remove("fitted"); node.style.removeProperty("--fit"); return; }
  node.style.setProperty("--fit", (fit / 100).toFixed(4));
  node.classList.add("fitted");
}

function applyLandscapeStage(view) {
  if (!view.stage) return;
  const ratio = view.landscape ? "1.41421356" : "0.7070707071";
  view.stage.style.aspectRatio = ratio;
  if (view.frame) view.frame.style.setProperty("--sheet", ratio);
  if (view.scroller) matchPaper(view, view.scroller);
}

function blank(view, number) {
  const sheet = el("div", { class: view.landscape ? "sheet is-landscape" : "sheet" });
  sheet.dataset.page = String(number);
  const media = el("div", { class: "sheet-media" });
  const face = el("div", { class: "sheet-face" });
  const left = el("div", { class: "half left" });
  const right = el("div", { class: "half right", attrs: { hidden: "hidden" } });
  const crease = el("i", { class: "crease", attrs: { hidden: "hidden", "aria-hidden": "true" } });
  left.append(pictureNode());
  right.append(pictureNode());
  face.append(left, crease, right);
  const slots = el("div", { class: "pair-slots", attrs: { hidden: "hidden" } });
  media.append(face, slots);
  sheet.append(media);
  sheet.addEventListener("click", (event) => onSheetClick(view, sheet, number, event));
  return sheet;
}

function pictureNode() {
  const img = document.createElement("img");
  img.alt = "";
  img.draggable = false;
  img.decoding = "async";
  return img;
}

function onSheetClick(view, sheet, number, event) {
  if (!view.canRotate) return;
  if (isPairView(view) && !view.landscape) { event.stopPropagation(); view.onClearSelection?.(); return; }
  event.stopPropagation();
  if (!view.landscape) { view.onSelectPage?.(number); return; }
  const mate = Number(sheet.dataset.mate) || 0;
  const box = sheet.getBoundingClientRect();
  const onRight = mate && event.clientX >= box.left + box.width / 2;
  view.onSelectPage?.(onRight ? mate : number);
}

function isPairView(view) {
  return Boolean(view.pair && Array.isArray(view.pair.boxes) && view.pair.boxes.length === 2);
}

function syncSelection(view) {
  if (!view.open || !view.stack) return;
  const pairActive = isPairView(view);
  syncRotateDock(view.dock, {
    canRotate: view.canRotate, busy: view.busyRotate, isPair: pairActive,
    selectedPage: pairActive ? null : view.selectedPage, selectedSlot: pairActive ? view.selectedSlot : null,
    pageCount: view.pageCount || 1, landscape: view.landscape,
  });
  for (const sheet of view.pool.values()) {
    const pageNum = Number(sheet.dataset.page);
    const mate = Number(sheet.dataset.mate) || 0;
    const selectable = view.canRotate && !pairActive;
    const picked = selectable && view.selectedPage === pageNum;
    const pickedMate = selectable && mate && view.selectedPage === mate;
    sheet.classList.toggle("is-selectable", selectable);
    sheet.classList.toggle("is-selected", picked && !view.landscape);
    sheet.classList.toggle("is-picked-left", Boolean(view.landscape && picked));
    sheet.classList.toggle("is-picked-right", Boolean(view.landscape && pickedMate));
    const slots = sheet.querySelector(".pair-slots");
    if (!slots) continue;
    if (pairActive && view.canRotate && pageNum === 1 && !view.landscape) paintPairSlots(slots, view.pair.boxes, view.selectedSlot, (index) => view.onSelectSlot?.(index));
    else paintPairSlots(slots, null, null, null);
  }
}

function listen(view, scroller, stack) {
  view.observer = new IntersectionObserver(() => {
    if (view.open) drawVisible(view, scroller, stack);
  }, { root: scroller, rootMargin: NEAR + "px 0px" });
  for (const sheet of stack.children) view.observer.observe(sheet);
  let width = scroller.clientWidth;
  view.resize = new ResizeObserver(() => {
    matchPaper(view, scroller);
    const next = scroller.clientWidth;
    if (!next || Math.abs(next - width) < 1) return;
    width = next;
    view.mark += 1;
    drawVisible(view, scroller, stack);
  });
  view.resize.observe(scroller);
}

function follow(view) {
  const token = ++view.follow;
  const step = () => {
    if (!view.open || view.follow !== token) return;
    if (view.ready >= view.pageCount) { paintWait(view); return; }
    fetch("/admin/jobs/" + view.id + "/previews").then((res) => (res.ok ? res.json() : null)).then((body) => {
      if (!view.open || view.follow !== token) return;
      if (body && body.ok) applyStatus(view, body);
      if (!view.open || view.follow !== token || view.ready >= view.pageCount) { paintWait(view); return; }
      view.poll = setTimeout(step, 400);
    }).catch(() => {
      if (view.open && view.follow === token) view.poll = setTimeout(step, 700);
    });
  };
  step();
}

function applyStatus(view, body) {
  const revision = String(body.revision || "");
  const ready = Number(body.ready) || 0;
  const moved = revision !== view.revision || ready !== view.ready;
  if (revision) view.revision = revision;
  view.ready = ready;
  paintWait(view);
  if (moved && view.stack) drawVisible(view, view.scroller, view.stack);
}

function paintWait(view) {
  const node = view.wait;
  if (!node) return;
  const total = view.pageCount || 0;
  const ready = view.ready || 0;
  const show = view.open && total > 0 && ready < total;
  node.hidden = !show;
  if (!show) return;
  node.classList.toggle("has-pages", ready > 0);
  const line = node.querySelector("p");
  const text = ready > 0 ? "Preparing preview, " + ready + " of " + total : "Preparing preview…";
  if (line && line.textContent !== text) line.textContent = text;
}

function kick(view) {
  if (view.running) { view.again = true; return; }
  view.running = true;
  settle(view).finally(() => {
    view.running = false;
    if (!view.open || !view.again) { view.again = false; return; }
    view.again = false;
    kick(view);
  });
}

/* The old view stays painted over the sheet, then dissolves once the new pages are in place. */
async function settle(view) {
  const numbers = wanted(view);
  const key = keyOf(numbers);
  if (!view.open || view.shown === key) return;
  const gen = ++view.gen;
  const animate = motionOk();
  const held = animate ? anchorOf(view.scroller) : null;
  if (animate && !view.veil) takeVeil(view);
  view.shown = key;
  mount(view, numbers);
  restoreScroll(view.scroller, held, numbers);
  if (!view.open || view.gen !== gen) return;
  syncSelection(view);
  drawVisible(view, view.scroller, view.stack);
  if (!animate) { dropVeil(view); return; }
  await whenDrawn(view, visibleSheet(view), gen);
  if (!view.open || view.gen !== gen || view.again || !view.veil) return;
  const veil = view.veil;
  view.veil = null;
  fadeVeil(veil);
}

function sourcePages(view) {
  const count = view.pageCount || 0;
  const pages = view.pages && view.pages.length ? view.pages : every(count);
  return pages.filter((number) => number >= 1 && number <= count);
}

function wanted(view) {
  const pages = sourcePages(view);
  if (!view.landscape) { view.mates = new Map(); return pages; }
  const pairs = landscapePairs(pages);
  view.mates = new Map(pairs.map(([left, right]) => [left, right || 0]));
  return pairs.map(([left]) => left);
}

function mateOf(view, pageNum) {
  if (!view.landscape || !view.mates) return 0;
  return view.mates.get(pageNum) || 0;
}

function every(count) {
  const pages = [];
  for (let number = 1; number <= count; number += 1) pages.push(number);
  return pages;
}

function keyOf(pages) { return pages.join(","); }

function mount(view, numbers) {
  const keep = new Set();
  const frag = document.createDocumentFragment();
  for (const number of numbers) {
    const sheet = sheetFor(view, number);
    const mate = view.landscape && view.mates ? view.mates.get(number) || 0 : 0;
    sheet.dataset.mate = mate ? String(mate) : "";
    sheet.classList.toggle("is-landscape", Boolean(view.landscape));
    keep.add(sheet);
    frag.append(sheet);
    view.observer?.observe(sheet);
  }
  if (view.pool) for (const sheet of view.pool.values()) if (!keep.has(sheet)) view.observer?.unobserve(sheet);
  view.stack.replaceChildren(frag);
}

function sheetFor(view, number) {
  const key = String(number);
  const found = view.pool.get(key);
  if (found) return found;
  const sheet = blank(view, number);
  view.pool.set(key, sheet);
  return sheet;
}

function anchorOf(scroller) {
  const top = scroller.scrollTop;
  for (const sheet of scroller.querySelectorAll(".sheet")) {
    if (sheet.offsetTop + sheet.offsetHeight > top + 1) return { page: Number(sheet.dataset.page), delta: sheet.offsetTop - top };
  }
  return null;
}

function restoreScroll(scroller, held, numbers) {
  if (!held || !numbers.length) { scroller.scrollTop = 0; return; }
  const page = numbers.includes(held.page) ? held.page : nearest(held.page, numbers);
  const sheet = [...scroller.querySelectorAll(".sheet")].find((node) => Number(node.dataset.page) === page);
  if (!sheet) { scroller.scrollTop = 0; return; }
  scroller.scrollTop = Math.max(0, sheet.offsetTop - (numbers.includes(held.page) ? held.delta : 0));
}

function nearest(page, numbers) {
  let best = numbers[0];
  let gap = Math.abs(best - page);
  for (const number of numbers) {
    const next = Math.abs(number - page);
    if (next < gap) { best = number; gap = next; }
  }
  return best;
}

function visibleSheet(view) {
  const top = view.scroller.scrollTop;
  for (const sheet of view.stack.children) if (sheet.offsetTop + sheet.offsetHeight > top + 1) return sheet;
  return view.stack.firstElementChild;
}

function whenDrawn(view, sheet, gen) {
  if (!sheet || sheet.dataset.drawn === String(view.mark)) return Promise.resolve();
  return new Promise((resolve) => {
    const deadline = performance.now() + 480;
    const tick = () => {
      if (!view.open || view.gen !== gen || sheet.dataset.drawn === String(view.mark) || performance.now() > deadline) resolve();
      else requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

function takeVeil(view) {
  const scroller = view.scroller;
  const width = scroller.clientWidth;
  const height = scroller.clientHeight;
  if (!width || !height || !view.stage) return null;
  const veil = document.createElement("canvas");
  veil.className = "sheet-veil";
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  veil.width = Math.max(1, Math.floor(width * dpr));
  veil.height = Math.max(1, Math.floor(height * dpr));
  veil.style.width = width + "px";
  veil.style.height = height + "px";
  const context = veil.getContext("2d");
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  const top = scroller.scrollTop;
  const scale = view.fit / 100;
  let painted = false;
  for (const sheet of view.stack.children) {
    const y = sheet.offsetTop;
    if (y + sheet.offsetHeight < top || y > top + height) continue;
    if (paintVeil(context, sheet, y - top, scale)) painted = true;
  }
  if (!painted) return null;
  view.stage.append(veil);
  view.veil = veil;
  return veil;
}

function paintVeil(context, sheet, dy, scale) {
  const width = sheet.clientWidth;
  const height = sheet.clientHeight;
  if (!width || !height) return false;
  let painted = false;
  context.save();
  context.beginPath();
  context.rect(0, dy, width, height);
  context.clip();
  if (Math.abs(scale - 1) > 0.001) {
    context.translate(width / 2, dy + height / 2);
    context.scale(scale, scale);
    context.translate(-width / 2, -(dy + height / 2));
  }
  for (const img of sheet.querySelectorAll(".half img")) {
    const half = img.parentElement;
    if (!img.naturalWidth || !half || half.hidden) continue;
    const w = parseFloat(img.style.width);
    const h = parseFloat(img.style.height);
    if (!w || !h) continue;
    const origin = cellOrigin(half, sheet);
    const turn = Number(img.dataset.turn) || 0;
    context.save();
    context.translate(origin.x + half.clientWidth / 2, dy + origin.y + half.clientHeight / 2);
    if (turn) context.rotate((turn * Math.PI) / 180);
    context.drawImage(img, -w / 2, -h / 2, w, h);
    context.restore();
    painted = true;
  }
  context.restore();
  return painted;
}

function cellOrigin(node, stop) {
  let x = 0;
  let y = 0;
  let current = node;
  while (current && current !== stop) { x += current.offsetLeft; y += current.offsetTop; current = current.offsetParent; }
  return { x, y };
}

function fadeVeil(veil) {
  const motion = veil.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 380, easing: "cubic-bezier(0.22, 0.61, 0.36, 1)", fill: "forwards" });
  const done = () => veil.remove();
  motion.finished.then(done, done);
}

function dropVeil(view) {
  view.veil?.remove();
  view.veil = null;
}

function motionOk() {
  return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function isNearViewport(scroller, sheet) {
  if (!scroller || !sheet) return false;
  const top = scroller.scrollTop - NEAR;
  const bottom = scroller.scrollTop + scroller.clientHeight + NEAR;
  return sheet.offsetTop + sheet.offsetHeight >= top && sheet.offsetTop <= bottom;
}

function drawVisible(view, scroller, stack) {
  releaseFar(view);
  if (!stack) return;
  for (const sheet of stack.children) if (isNearViewport(scroller, sheet)) placeSheet(view, sheet);
}

function placeSheet(view, sheet) {
  const pageNum = Number(sheet.dataset.page);
  const mate = mateOf(view, pageNum);
  const right = sheet.querySelector(".half.right");
  const crease = sheet.querySelector(".crease");
  sheet.classList.toggle("is-landscape", Boolean(view.landscape));
  if (right) right.hidden = !(view.landscape && mate);
  if (crease) crease.hidden = !(view.landscape && mate);
  showHalf(view, sheet.querySelector(".half.left"), pageNum);
  if (view.landscape && mate) showHalf(view, right, mate);
  else if (right) releasePicture(right.querySelector("img"));
  sheet.dataset.drawn = String(view.mark);
}

function showHalf(view, half, pageNum) {
  if (!half || !pageNum) return;
  const img = half.querySelector("img");
  const url = pageNum <= view.ready ? pictureUrl(view.id, pageNum, view.revision) : "";
  if (!img || !url) return;
  loadPicture(img, url, () => reveal(img, rotOf(view, pageNum)));
}

function reveal(img, turn) {
  const fresh = !img.classList.contains("is-placed");
  placePicture(img, turn);
  if (fresh) requestAnimationFrame(() => { if (img.isConnected) img.classList.add("is-placed"); });
}

function releaseFar(view) {
  if (!view.pool || !view.scroller) return;
  for (const sheet of view.pool.values()) {
    if (sheet.isConnected && isNearViewport(view.scroller, sheet)) continue;
    releaseSheet(sheet);
    sheet.dataset.drawn = "";
  }
}

function releaseSheet(sheet) {
  for (const img of sheet.querySelectorAll("img")) releasePicture(img);
}

function rotOf(view, pageNum) {
  const turn = ((Math.round(Number(view.rotations && view.rotations[pageNum])) || 0) % 360 + 360) % 360;
  return turn === 90 || turn === 180 || turn === 270 ? turn : 0;
}

function current(view, slot) { return view.open && slot.dataset.key === view.id; }
