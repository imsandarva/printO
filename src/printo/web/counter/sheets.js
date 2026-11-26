/* The sheet on the desk. Drawn here, so the browser's PDF window never frames it.
   The sheet is always A4, portrait, the paper that prints. A page keeps its own shape and sits in the middle.
   The phone keeps the viewer; this page uses that same copy.
   A page choice only changes which sheets are on the desk. The file stays open. */

import * as pdfjs from "/c/pdf.min.mjs";
import { holdPages } from "./bar.js";
import { el } from "./dom.js";
import { clampFit, sizeControl } from "./fit.js";
import { createRotateDock, flickIcon, paintPairSlots, syncRotateDock } from "./rotate.js";

const WORKER = "/c/pdf.worker.min.mjs";
const NEAR = 480;

pdfjs.GlobalWorkerOptions.workerSrc = WORKER;

let live = null;

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

function blank(view, number) {
  const sheet = el("div", { class: "sheet" });
  sheet.dataset.page = String(number);
  const media = el("div", { class: "sheet-media" });
  const slots = el("div", { class: "pair-slots", attrs: { hidden: "hidden" } });
  media.append(el("canvas"), slots);
  sheet.append(media);
  sheet.addEventListener("click", (event) => {
    if (!view.canRotate) return;
    if (isPairView(view)) {
      event.stopPropagation();
      view.onClearSelection?.();
      return;
    }
    event.stopPropagation();
    view.onSelectPage?.(number);
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
  });
  for (const sheet of view.pool.values()) {
    const pageNum = Number(sheet.dataset.page);
    const selectable = view.canRotate && !pairActive;
    sheet.classList.toggle("is-selectable", selectable);
    sheet.classList.toggle("is-selected", selectable && view.selectedPage === pageNum);
    const slots = sheet.querySelector(".pair-slots");
    if (slots) {
      if (pairActive && view.canRotate && pageNum === 1) {
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

function wanted(view) {
  const count = view.doc ? view.doc.numPages : 0;
  const pages = view.pages && view.pages.length ? view.pages : every(count);
  return pages.filter((number) => number >= 1 && number <= count);
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
  for (const sheet of stack.children) if (isNearViewport(scroller, sheet)) draw(view, sheet);
}

async function draw(view, sheet) {
  const mark = String(view.mark);
  if (!view.open || !view.doc || sheet.dataset.drawn === mark || sheet.dataset.drawing === mark) return;
  sheet.dataset.drawing = mark;
  let page = null;
  try {
    const pageNum = Number(sheet.dataset.page);
    page = await view.doc.getPage(pageNum);
    if (!drawing(view, sheet, mark)) return;
    const canvas = sheet.querySelector(".sheet-media > canvas");
    const task = paint(view, sheet, page, canvas);
    if (!task || !drawing(view, sheet, mark)) return;
    view.tasks.push(task);
    await task.promise;
    if (drawing(view, sheet, mark)) sheet.dataset.drawn = mark;
  } catch {
    /* A cancelled draw, or a page that cannot be shown. The file can still be printed. */
  } finally {
    if (page) page.cleanup();
    if (sheet.dataset.drawing === mark) sheet.dataset.drawing = "";
  }
}

async function turnSheet(view, sheet) {
  const mark = String(view.mark);
  const turn = String((Number(sheet.dataset.turn || 0) || 0) + 1);
  sheet.dataset.turn = turn;
  sheet.dataset.drawing = mark;
  let page = null;
  try {
    const pageNum = Number(sheet.dataset.page);
    page = await view.doc.getPage(pageNum);
    if (!view.open || sheet.dataset.turn !== turn) return;
    const frame = frameOf(sheet);
    const oldCanvas = sheet.querySelector(".sheet-media > canvas");
    if (!frame || !oldCanvas) return;

    const base = page.rotate || 0;
    const prevRot = oldCanvas.dataset.rot != null ? Number(oldCanvas.dataset.rot) : base;
    const nextRot = (base + ((view.rotations && view.rotations[pageNum]) || 0)) % 360;
    const curScale = fitScale(frame, page.getViewport({ scale: 1, rotation: prevRot }));
    const nextScale = fitScale(frame, page.getViewport({ scale: 1, rotation: nextRot }));
    const ratio = curScale > 0 ? nextScale / curScale : 1;
    const delta = ((nextRot - prevRot) % 360 + 360) % 360;

    const off = document.createElement("canvas");
    const task = paint(view, sheet, page, off);
    if (!task) return;
    view.tasks.push(task);

    let animDone = Promise.resolve();
    if (motionOk() && delta && oldCanvas.width > 0) {
      oldCanvas.getAnimations().forEach((a) => a.cancel());
      const anim = oldCanvas.animate(
        [
          { transform: "rotate(0deg) scale(1)" },
          { transform: "rotate(" + delta + "deg) scale(" + ratio.toFixed(4) + ")" },
        ],
        { duration: 210, easing: "cubic-bezier(0.22, 1, 0.36, 1)", fill: "forwards" },
      );
      animDone = anim.finished.catch(() => {});
    }

    await Promise.all([task.promise, animDone]);
    if (!view.open || sheet.dataset.turn !== turn) return;
    oldCanvas.replaceWith(off);
    sheet.dataset.drawn = mark;
  } catch {
    /* A superseded turn or cancelled render. */
  } finally {
    if (page) page.cleanup();
    if (sheet.dataset.drawing === mark) sheet.dataset.drawing = "";
  }
}

async function swapSheet(view, sheet) {
  const mark = String(view.mark);
  const turn = String((Number(sheet.dataset.turn || 0) || 0) + 1);
  sheet.dataset.turn = turn;
  sheet.dataset.drawing = mark;
  let page = null;
  try {
    const pageNum = Number(sheet.dataset.page);
    page = await view.doc.getPage(pageNum);
    if (!view.open || sheet.dataset.turn !== turn) return;
    const oldCanvas = sheet.querySelector(".sheet-media > canvas");
    if (!oldCanvas) return;
    const off = document.createElement("canvas");
    const task = paint(view, sheet, page, off);
    if (!task) return;
    view.tasks.push(task);
    await task.promise;
    if (!view.open || sheet.dataset.turn !== turn) return;
    if (motionOk() && oldCanvas.width > 0) {
      off.style.opacity = "0";
      oldCanvas.after(off);
      const fadeIn = off.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 180, easing: "cubic-bezier(0.22, 1, 0.36, 1)", fill: "forwards" });
      await fadeIn.finished.catch(() => {});
      if (!view.open || sheet.dataset.turn !== turn) { off.remove(); return; }
      off.style.opacity = "";
      fadeIn.cancel();
      oldCanvas.remove();
    } else {
      oldCanvas.replaceWith(off);
    }
    sheet.dataset.drawn = mark;
  } catch {
    /* A superseded swap. */
  } finally {
    if (page) page.cleanup();
    if (sheet.dataset.drawing === mark) sheet.dataset.drawing = "";
  }
}

/* The sheet is A4. The page keeps its shape and sits in the middle; the rest of the sheet stays white. */
function paint(view, sheet, page, canvas) {
  const frame = frameOf(sheet);
  const pageNum = Number(sheet.dataset.page);
  const extra = (view.rotations && view.rotations[pageNum]) || 0;
  const rotation = ((page.rotate || 0) + extra) % 360;
  const natural = page.getViewport({ scale: 1, rotation });
  if (!frame || !natural.width || !natural.height || !canvas) return null;
  const viewport = page.getViewport({ scale: fitScale(frame, natural), rotation });
  prepare(canvas, frame, rotation);
  return page.render({ canvasContext: canvas.getContext("2d", { alpha: false }), viewport, transform: shift(frame, viewport) });
}

function frameOf(sheet) {
  const width = sheet.clientWidth;
  const height = sheet.clientHeight;
  return width && height ? { width, height } : null;
}

function fitScale(frame, natural) { return Math.min(frame.width / natural.width, frame.height / natural.height); }

function prepare(canvas, frame, rotation) {
  const dpr = pixels();
  canvas.width = Math.max(1, Math.floor(frame.width * dpr));
  canvas.height = Math.max(1, Math.floor(frame.height * dpr));
  canvas.dataset.rot = String(rotation);
  return canvas;
}

function shift(frame, viewport) {
  const dpr = pixels();
  const dx = (frame.width - viewport.width) / 2;
  const dy = (frame.height - viewport.height) / 2;
  return [dpr, 0, 0, dpr, dx * dpr, dy * dpr];
}

function pixels() { return Math.min(window.devicePixelRatio || 1, 2); }

function drawing(view, sheet, mark) { return view.open && sheet.dataset.drawing === mark; }

function current(view, slot) { return view.open && slot.dataset.key === view.id; }

function fail(slot, text) { slot.replaceChildren(el("p", { class: "quiet", text })); }
