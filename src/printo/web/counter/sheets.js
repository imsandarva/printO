/* The sheet on the desk. Drawn here, so the browser's PDF window never frames it.
   The sheet is always A4, portrait, the paper that prints. A page keeps its own shape and sits in the middle.
   The phone keeps the viewer; this page uses that same copy.
   A page choice only changes which sheets are on the desk. The file stays open. */

import * as pdfjs from "/c/pdf.min.mjs";
import { holdPages } from "./bar.js";
import { el } from "./dom.js";
import { clampFit, sizeControl } from "./fit.js";
import { landscapePairs, paintLandscapeSheet } from "./landscape.js";
import { cellNeed, clearProxies, createProxyCache, dropProxy, evictProxies, holdProxy, pageProxy, paintSheet, peekProxy, proxySharp, quarter, rasterEdge, turnRatio } from "./proxy.js";
import { createRotateDock, flickIcon, paintPairSlots, syncRotateDock } from "./rotate.js";

const WORKER = "/c/pdf.worker.min.mjs";
const NEAR = 480;

pdfjs.GlobalWorkerOptions.workerSrc = WORKER;

let live = null;
const waits = new WeakMap();

export function closeSheets() {
  if (!live) return;
  const view = live;
  live = null;
  shutdown(view);
}

export function showSheets(slot, id, bytes, copy) {
  closeSheets();
  const view = {
    id, open: true, mark: 1, doc: null, tasks: [], observer: null, resize: null, hold: null, root: null,
    fit: clampFit(copy.fit), onFit: copy.onFit || null, caption: copy.caption, fail: copy.fail,
    pages: copy.pages ? copy.pages.slice() : null, pool: new Map(), stack: null, scroller: null, frame: null,
    stage: null, dock: null, shown: null, gen: 0, docGen: 0, veil: null, timer: 0, running: false, again: false,
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
    cache: createProxyCache(),
  };
  live = view;
  read(view, slot, bytes);
}

/* Which pages will print. Called again as the choice changes; the PDF is not opened twice. */
export function focusSheets(pages) {
  if (!live || !pages || !pages.length) return;
  live.pages = pages.slice();
  if (!live.stack) return;
  if (live.timer) clearTimeout(live.timer);
  live.timer = setTimeout(() => { live.timer = 0; if (live && live.open) kick(live); }, 80);
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

/* Toggle landscape 2-up. The old picture is dropped in this same turn, then the
   pictures already on screen are laid into the new shape. A missing half stays blank. */
export function setLandscapeMode(on) {
  if (!live || !live.open) return;
  live.landscape = Boolean(on);
  live.mark += 1;
  dropVeil(live);
  applyLandscapeStage(live);
  if (live.pool) {
    for (const sheet of live.pool.values()) {
      forget(sheet);
      sheet.classList.toggle("is-landscape", live.landscape);
      clearPicture(sheet);
    }
  }
  if (live.stack) {
    const numbers = wanted(live);
    live.shown = keyOf(numbers);
    mount(live, numbers);
    showHeld(live);
    if (live.scroller) drawVisible(live, live.scroller, live.stack);
  }
  syncSelection(live);
}

export function rotateSheetsInPlace(rotations, targetPages) {
  if (!live || !live.open || !live.doc || !live.stack) return;
  live.rotations = { ...rotations };
  live.mark += 1;
  const targets = targetPages && targetPages.length ? new Set(targetPages) : null;
  for (const sheet of live.pool.values()) {
    const num = Number(sheet.dataset.page);
    if (targets && !targets.has(num)) continue;
    if (sheet.isConnected && isNearViewport(live.scroller, sheet)) turnSheet(live, sheet);
    else { forget(sheet); if (sheet.isConnected) draw(live, sheet); }
  }
}

export async function replaceSheetsDocument(bytes, next = {}) {
  if (!live || !live.open || !live.stack) return;
  const view = live;
  const docGen = ++view.docGen;
  let newDoc = null;
  try {
    newDoc = await openDocument(bytes);
    if (!view.open || view.docGen !== docGen) return;
    cancel(view);
    clearProxies(view.cache);
    const oldDoc = view.doc;
    view.doc = newDoc;
    newDoc = null;
    if ("pair" in next) view.pair = next.pair;
    if ("canRotate" in next) view.canRotate = Boolean(next.canRotate);
    if ("selectedPage" in next) view.selectedPage = next.selectedPage;
    if ("selectedSlot" in next) view.selectedSlot = next.selectedSlot;
    if ("rotations" in next) view.rotations = { ...(next.rotations || {}) };
    view.mark += 1;
    for (const sheet of view.pool.values()) {
      if (sheet.isConnected && isNearViewport(view.scroller, sheet)) swapSheet(view, sheet);
      else forget(sheet);
    }
    syncSelection(view);
    if (oldDoc) oldDoc.destroy();
  } catch {
    /* Keep the previous crisp document if a replacement read is aborted. */
  } finally {
    if (newDoc) newDoc.destroy();
  }
}

export function pulseRotateButton() {
  if (!live || !live.dock) return;
  flickIcon(live.dock.querySelector(".rotate-btn"));
}

function shutdown(view) {
  view.open = false;
  view.gen += 1;
  view.docGen += 1;
  if (view.timer) clearTimeout(view.timer);
  view.veil?.remove();
  view.veil = null;
  view.hold?.close();
  view.observer?.disconnect();
  view.resize?.disconnect();
  cancel(view);
  if (view.pool) for (const sheet of view.pool.values()) clearWait(sheet);
  clearProxies(view.cache);
  view.pool = null;
  const doc = view.doc;
  view.doc = null;
  if (doc) doc.destroy();
}

function cancel(view) {
  for (const task of view.tasks) task.cancel?.();
  view.tasks.length = 0;
}

async function read(view, slot, bytes) {
  let doc = null;
  try {
    doc = await openDocument(bytes);
    if (!current(view, slot)) return;
    view.doc = doc;
    doc = null;
    await place(view, slot);
  } catch {
    if (current(view, slot)) fail(slot, view.fail);
  } finally {
    if (doc) doc.destroy();
  }
}

function openDocument(bytes) {
  return pdfjs.getDocument({ data: bytes.slice(), disableAutoFetch: true, disableStream: true, isEvalSupported: false, useSystemFonts: true }).promise;
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
  held.frame.insertBefore(stage, scroller);
  stage.append(scroller);
  const preview = column(held.frame, dock, view);
  if (!current(view, slot)) { held.close(); return; }
  view.hold = held;
  view.root = preview;
  view.frame = held.frame;
  view.stage = stage;
  view.dock = dock;
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
  syncSelection(view);
  requestAnimationFrame(() => drawVisible(view, scroller, stack));
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

/* Scale the already-drawn page. Redrawing it on every move would stutter. */
function matchPaper(view, scroller) {
  const width = scroller.clientWidth;
  if (view.root && width) view.root.style.setProperty("--paper", width + "px");
}

function applyScale(node, fit) {
  if (!node) return;
  // 100 is the drawn page, left unscaled so it stays sharp. Above that, the sheet cuts off whatever passes the edge.
  if (Math.abs(fit - 100) < 0.05) { node.classList.remove("fitted"); node.style.removeProperty("--fit"); return; }
  node.style.setProperty("--fit", (fit / 100).toFixed(4));
  node.classList.add("fitted");
}

/* Switch stage and sheet-frame aspect-ratio between landscape (2-up) and portrait. */
function applyLandscapeStage(view) {
  if (!view.stage) return;
  /* A4 portrait: 210/297 ≈ 0.7071. Landscape: 297/210 ≈ 1.4142. */
  const ratio = view.landscape ? "1.41421356" : "0.7070707071";
  /* Override the stage aspect-ratio inline so it beats the CSS var(--sheet). */
  view.stage.style.aspectRatio = ratio;
  /* Widen/narrow the sheet-frame by updating --sheet on the frame element. */
  const frameEl = view.frame;
  if (frameEl) frameEl.style.setProperty("--sheet", ratio);
  /* Trigger a paper-width sync so the dock/caption align. */
  if (view.scroller) matchPaper(view, view.scroller);
}

function blank(view, number) {
  const sheet = el("div", { class: "sheet" });
  sheet.dataset.page = String(number);
  /* In landscape 2-up mode, each sheet card is wider (landscape ratio). */
  if (view.landscape) sheet.classList.add("is-landscape");
  const media = el("div", { class: "sheet-media" });
  const slots = el("div", { class: "pair-slots", attrs: { hidden: "hidden" } });
  const hold = el("div", { class: "sheet-hold", attrs: { "aria-hidden": "true" } });
  hold.append(el("span", { class: "spin" }), el("p", { class: "quiet", text: "Preparing this page…" }));
  media.append(el("canvas"), hold, slots);
  sheet.append(media);
  sheet.addEventListener("click", (event) => {
    if (!view.canRotate) return;
    if (isPairView(view) && !view.landscape) {
      event.stopPropagation();
      view.onClearSelection?.();
      return;
    }
    event.stopPropagation();
    if (!view.landscape) { view.onSelectPage?.(number); return; }
    const mate = Number(sheet.dataset.mate) || 0;
    const box = sheet.getBoundingClientRect();
    const onRight = mate && event.clientX >= box.left + box.width / 2;
    view.onSelectPage?.(onRight ? mate : number);
  });
  return sheet;
}

function isPairView(view) {
  return Boolean(view.pair && Array.isArray(view.pair.boxes) && view.pair.boxes.length === 2);
}

function syncSelection(view) {
  if (!view.open || !view.stack) return;
  const pairActive = isPairView(view);
  const pageCount = view.doc ? view.doc.numPages : 1;
  syncRotateDock(view.dock, {
    canRotate: view.canRotate,
    busy: view.busyRotate,
    isPair: pairActive,
    selectedPage: pairActive ? null : view.selectedPage,
    selectedSlot: pairActive ? view.selectedSlot : null,
    pageCount,
    landscape: view.landscape,
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
    if (slots) {
      if (pairActive && view.canRotate && pageNum === 1 && !view.landscape) {
        paintPairSlots(slots, view.pair.boxes, view.selectedSlot, (index) => view.onSelectSlot?.(index));
      } else {
        paintPairSlots(slots, null, null, null);
      }
    }
  }
}

function listen(view, scroller, stack) {
  view.observer = new IntersectionObserver((entries) => {
    for (const entry of entries) if (entry.isIntersecting) draw(view, entry.target);
  }, { root: scroller, rootMargin: NEAR + "px 0px" });
  for (const sheet of stack.children) view.observer.observe(sheet);
  let width = scroller.clientWidth;
  view.resize = new ResizeObserver(() => {
    matchPaper(view, scroller);
    const next = scroller.clientWidth;
    if (!next || Math.abs(next - width) < 1) return;
    width = next;
    retarget(view, scroller, stack);
  });
  view.resize.observe(scroller);
}

function retarget(view, scroller, stack) {
  cancel(view);
  view.mark += 1;
  for (const sheet of stack.children) forget(sheet);
  if (view.pool) for (const sheet of view.pool.values()) forget(sheet);
  drawVisible(view, scroller, stack);
}

function forget(sheet) { sheet.dataset.drawn = ""; sheet.dataset.drawing = ""; }

/* Drop the bitmap before the sheet changes shape, so the old picture cannot be stretched into it. */
function clearPicture(sheet) {
  const canvas = sheet.querySelector(".sheet-media > canvas");
  if (canvas) { canvas.width = 0; canvas.height = 0; delete canvas.dataset.rot; delete canvas.dataset.landscape; }
  sheet.classList.remove("is-ready");
  clearWait(sheet);
}

/* Lay the pictures we already have into the sheet that is on screen. No file is opened here. */
function showHeld(view) {
  if (!view.open || !view.stack || !view.doc) return;
  const mark = String(view.mark);
  for (const sheet of view.stack.children) {
    if (!isNearViewport(view.scroller, sheet)) continue;
    const frame = frameOf(sheet);
    const canvas = sheet.querySelector(".sheet-media > canvas");
    if (!frame || !canvas) continue;
    const pageNum = Number(sheet.dataset.page);
    const rightNum = mateOf(view, pageNum);
    const left = peekProxy(view.cache, pageNum);
    const right = rightNum ? peekProxy(view.cache, rightNum) : null;
    if (!left && !right) continue;
    stampSheet(view, sheet, canvas, frame, left, right, pageNum, rightNum);
    if (sideReady(left, frame, view.landscape) && (!rightNum || sideReady(right, frame, true))) sheet.dataset.drawn = mark;
  }
}

function sideReady(proxy, frame, half) { return proxySharp(proxy, cellNeed(frame, half)); }

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

/* The old view stays painted over the sheet, then dissolves once the new pages are ready. */
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
  // A newer choice arrived while this one was settling. Keep the veil and let that choice fade once.
  if (!view.open || view.gen !== gen || view.again || !view.veil) return;
  const veil = view.veil;
  view.veil = null;
  fadeVeil(veil);
}

function sourcePages(view) {
  const count = view.doc ? view.doc.numPages : 0;
  const pages = view.pages && view.pages.length ? view.pages : every(count);
  return pages.filter((number) => number >= 1 && number <= count);
}

function wanted(view) {
  const pages = sourcePages(view);
  if (!view.landscape) { view.mates = new Map(); return pages; }
  /* Pair the pages that will print, in that order. Page 1 beside page 3 when only the odd ones are chosen. */
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
  const canvas = sheet.querySelector(".sheet-media > canvas");
  if (!canvas || !canvas.width) return false;
  const width = sheet.clientWidth;
  const height = sheet.clientHeight;
  if (!width || !height) return false;
  context.save();
  context.beginPath();
  context.rect(0, dy, width, height);
  context.clip();
  if (Math.abs(scale - 1) > 0.001) {
    context.translate(width / 2, dy + height / 2);
    context.scale(scale, scale);
    context.translate(-width / 2, -(dy + height / 2));
  }
  context.drawImage(canvas, 0, dy, width, height);
  context.restore();
  return true;
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
  for (const sheet of stack.children) if (isNearViewport(scroller, sheet)) draw(view, sheet);
}

async function draw(view, sheet) {
  const mark = String(view.mark);
  if (!view.open || !view.doc || sheet.dataset.drawn === mark || sheet.dataset.drawing === mark) return;
  sheet.dataset.drawing = mark;
  const canvas = sheet.querySelector(".sheet-media > canvas");
  try {
    const ok = await repaint(view, sheet, canvas, () => drawing(view, sheet, mark));
    if (ok && drawing(view, sheet, mark)) sheet.dataset.drawn = mark;
    else if (drawing(view, sheet, mark)) clearWait(sheet);
  } catch {
    /* A cancelled draw, or a page that cannot be shown. The file can still be printed. */
  } finally {
    if (sheet.dataset.drawing === mark) sheet.dataset.drawing = "";
  }
}

async function turnSheet(view, sheet) {
  const mark = String(view.mark);
  const turn = String((Number(sheet.dataset.turn || 0) || 0) + 1);
  sheet.dataset.turn = turn;
  sheet.dataset.drawing = mark;
  const frame = frameOf(sheet);
  const oldCanvas = sheet.querySelector(".sheet-media > canvas");
  if (!frame || !oldCanvas) { sheet.dataset.drawing = ""; return; }
  const pageNum = Number(sheet.dataset.page);
  const prev = oldCanvas.dataset.rot != null ? quarter(oldCanvas.dataset.rot) : 0;
  const next = rotOf(view, pageNum);
  const delta = ((next - prev) % 360 + 360) % 360;
  const ratio = turnRatio(frame, peekProxy(view.cache, pageNum), prev, next);
  let animDone = Promise.resolve();
  if (!view.landscape && motionOk() && delta && oldCanvas.width > 0) {
    oldCanvas.getAnimations().forEach((anim) => anim.cancel());
    animDone = oldCanvas.animate(
      [{ transform: "rotate(0deg) scale(1)" }, { transform: "rotate(" + delta + "deg) scale(" + ratio.toFixed(4) + ")" }],
      { duration: 210, easing: "cubic-bezier(0.22, 1, 0.36, 1)", fill: "forwards" },
    ).finished.catch(() => {});
  }
  const off = document.createElement("canvas");
  try {
    const ok = await repaint(view, sheet, off, () => view.open && sheet.dataset.turn === turn);
    if (!ok || !view.open || sheet.dataset.turn !== turn) { if (!view.open || sheet.dataset.turn === turn) clearWait(sheet); return; }
    await animDone;
    if (!view.open || sheet.dataset.turn !== turn) return;
    oldCanvas.replaceWith(off);
    sheet.dataset.drawn = mark;
  } catch {
    /* A superseded turn. The previous picture stays until the next one is ready. */
  } finally {
    if (sheet.dataset.drawing === mark) sheet.dataset.drawing = "";
  }
}

async function swapSheet(view, sheet) {
  const mark = String(view.mark);
  const turn = String((Number(sheet.dataset.turn || 0) || 0) + 1);
  sheet.dataset.turn = turn;
  sheet.dataset.drawing = mark;
  const oldCanvas = sheet.querySelector(".sheet-media > canvas");
  if (!oldCanvas) { sheet.dataset.drawing = ""; return; }
  const off = document.createElement("canvas");
  try {
    const ok = await repaint(view, sheet, off, () => view.open && sheet.dataset.turn === turn);
    if (!ok || !view.open || sheet.dataset.turn !== turn) { if (!view.open || sheet.dataset.turn === turn) clearWait(sheet); return; }
    if (motionOk() && oldCanvas.width > 0) {
      off.style.opacity = "0";
      oldCanvas.after(off);
      const fadeIn = off.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 180, easing: "cubic-bezier(0.22, 1, 0.36, 1)", fill: "forwards" });
      await fadeIn.finished.catch(() => {});
      if (!view.open || sheet.dataset.turn !== turn) { off.remove(); return; }
      off.style.opacity = "";
      fadeIn.cancel();
      oldCanvas.remove();
    } else oldCanvas.replaceWith(off);
    sheet.dataset.drawn = mark;
  } catch {
    /* A superseded swap. */
  } finally {
    if (sheet.dataset.drawing === mark) sheet.dataset.drawing = "";
  }
}

/* Draw from the screen picture when it exists. Open the file only for a half that has no picture yet.
   A half that is not ready stays empty. The previous picture is never stretched into the new shape. */
async function repaint(view, sheet, canvas, still) {
  const frame = frameOf(sheet);
  const pageNum = Number(sheet.dataset.page);
  if (!frame || !canvas || !view.doc || !still()) return false;
  const rightNum = mateOf(view, pageNum);
  let left = peekProxy(view.cache, pageNum);
  let right = rightNum ? peekProxy(view.cache, rightNum) : null;
  if (left || right) stampSheet(view, sheet, canvas, frame, left, right, pageNum, rightNum);
  const leftNeed = !sideReady(left, frame, view.landscape);
  const rightNeed = Boolean(rightNum) && !sideReady(right, frame, true);
  if (!leftNeed && !rightNeed) return Boolean(left);
  if (!left && !right) expectWait(sheet);
  const edge = rasterEdge(frame);
  let heldLeft = false;
  let heldRight = false;
  try {
    if (leftNeed) {
      left = await pageProxy(view.cache, view.doc, pageNum, edge, hooksOf(view));
      if (!left || !still()) return false;
      holdProxy(left);
      heldLeft = true;
    }
    if (rightNeed && still()) {
      right = await pageProxy(view.cache, view.doc, rightNum, edge, hooksOf(view));
      if (!still()) return false;
      if (right) { holdProxy(right); heldRight = true; }
    }
    if (!still() || (!left && !right)) return false;
    stampSheet(view, sheet, canvas, frame, left, right, pageNum, rightNum);
    return true;
  } finally {
    if (heldLeft) dropProxy(left);
    if (heldRight) dropProxy(right);
  }
}

function stampSheet(view, sheet, canvas, frame, left, right, pageNum, rightNum) {
  if (view.landscape) paintLandscapeSheet(canvas, frame, left, right, rotOf(view, pageNum), right ? rotOf(view, rightNum) : 0);
  else paintSheet(canvas, frame, left, rotOf(view, pageNum));
  settleWait(sheet);
  warm(view, pageNum, rasterEdge(frame));
  const keep = retained(view);
  keep.add(pageNum);
  if (rightNum) keep.add(rightNum);
  evictProxies(view.cache, keep);
  releaseFar(view);
}

function warm(view, pageNum, edge) {
  const ahead = [];
  const mate = mateOf(view, pageNum);
  if (mate) ahead.push(mate);
  const leaders = view.landscape && view.mates ? [...view.mates.keys()] : [];
  const at = leaders.indexOf(pageNum);
  if (at >= 0 && leaders[at + 1]) ahead.push(leaders[at + 1], view.mates.get(leaders[at + 1]) || 0);
  else if (!view.landscape) ahead.push(pageNum + 1);
  for (const next of ahead) {
    if (!next || !view.doc || next > view.doc.numPages || peekProxy(view.cache, next)) continue;
    pageProxy(view.cache, view.doc, next, edge, hooksOf(view)).catch(() => {});
  }
}

function retained(view) {
  const keep = new Set();
  const last = view.doc ? view.doc.numPages : 0;
  if (!view.stack) return keep;
  for (const sheet of view.stack.children) {
    if (!isNearViewport(view.scroller, sheet)) continue;
    const num = Number(sheet.dataset.page);
    keep.add(num);
    if (num < last) keep.add(num + 1);
  }
  return keep;
}

function releaseFar(view) {
  if (!view.pool || !view.scroller) return;
  for (const sheet of view.pool.values()) {
    if (!sheet.isConnected || sheet.dataset.drawing || isNearViewport(view.scroller, sheet)) continue;
    const canvas = sheet.querySelector(".sheet-media > canvas");
    if (!canvas || !canvas.width) continue;
    canvas.width = 0;
    canvas.height = 0;
    sheet.dataset.drawn = "";
    sheet.classList.remove("is-ready");
    clearWait(sheet);
  }
}

function expectWait(sheet) {
  if (waits.has(sheet) || sheet.classList.contains("is-ready") || sheet.classList.contains("is-waiting")) return;
  waits.set(sheet, setTimeout(() => { if (!sheet.classList.contains("is-ready")) sheet.classList.add("is-waiting"); }, 180));
}

function settleWait(sheet) {
  clearWait(sheet);
  sheet.classList.add("is-ready");
}

function clearWait(sheet) {
  const timer = waits.get(sheet);
  if (timer) clearTimeout(timer);
  waits.delete(sheet);
  sheet.classList.remove("is-waiting");
}

function rotOf(view, pageNum) { return quarter((view.rotations && view.rotations[pageNum]) || 0); }

function hooksOf(view) {
  const stamp = view.cache.stamp;
  return { alive: () => Boolean(view.open && view.cache.stamp === stamp), track: (task) => { view.tasks.push(task); const drop = () => { const index = view.tasks.indexOf(task); if (index >= 0) view.tasks.splice(index, 1); }; task.promise.then(drop, drop); } };
}

function frameOf(sheet) {
  const width = sheet.clientWidth;
  const height = sheet.clientHeight;
  return width && height ? { width, height } : null;
}

function drawing(view, sheet, mark) { return view.open && sheet.dataset.drawing === mark; }

function current(view, slot) { return view.open && slot.dataset.key === view.id; }

function fail(slot, text) { slot.replaceChildren(el("p", { class: "quiet", text })); }
