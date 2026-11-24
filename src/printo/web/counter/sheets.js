/* The sheet on the desk. Drawn here, so the browser's PDF window never frames it.
   The phone keeps the viewer; this page uses that same copy.
   A page choice only changes which sheets are on the desk. The file stays open. */

import * as pdfjs from "/c/pdf.min.mjs";
import { holdPages } from "./bar.js";
import { el } from "./dom.js";
import { clampFit, sizeControl } from "./fit.js";

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
    ratio: 0, shown: null, gen: 0, veil: null, timer: 0, running: false, again: false,
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

function shutdown(view) {
  view.open = false;
  view.gen += 1;
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

async function place(view, slot) {
  const first = await view.doc.getPage(1);
  if (!view.open) { first.cleanup(); return; }
  const ratio = ratioOf(first);
  first.cleanup();
  if (!current(view, slot)) return;
  const scroller = el("div", { class: "sheet-page", attrs: { role: "region", "aria-label": "Pages" } });
  const stack = el("div", { class: "sheet-stack" });
  scroller.append(stack);
  if (!current(view, slot)) return;
  const held = holdPages(scroller);
  const preview = column(held.frame, ratio, view);
  if (!current(view, slot)) { held.close(); return; }
  view.hold = held;
  view.root = preview;
  view.frame = held.frame;
  view.scroller = scroller;
  view.stack = stack;
  view.ratio = ratio;
  slot.replaceChildren(preview);
  matchPaper(view, scroller);
  if (!view.open) return;
  listen(view, scroller, stack);
  const pages = wanted(view);
  mount(view, pages);
  view.shown = keyOf(pages);
  requestAnimationFrame(() => drawVisible(view, scroller, stack));
}

function column(frame, ratio, view) {
  const preview = el("div", { class: "preview" });
  preview.style.setProperty("--sheet", String(ratio));
  frame.style.setProperty("--sheet", String(ratio));
  preview.append(frame);
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

function ratioOf(page) {
  const box = page.getViewport({ scale: 1 });
  return box.width / box.height;
}

function blank(number, ratio) {
  const sheet = el("div", { class: "sheet" });
  sheet.dataset.page = String(number);
  sheet.style.aspectRatio = String(ratio);
  sheet.append(el("canvas"));
  return sheet;
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
  const sheet = blank(number, view.ratio);
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
  if (!width || !height || !view.frame) return null;
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
  view.frame.append(veil);
  view.veil = veil;
  return veil;
}

function paintVeil(context, sheet, dy, scale) {
  const canvas = sheet.querySelector("canvas");
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

function drawVisible(view, scroller, stack) {
  const top = scroller.scrollTop - NEAR;
  const bottom = scroller.scrollTop + scroller.clientHeight + NEAR;
  for (const sheet of stack.children) if (sheet.offsetTop + sheet.offsetHeight >= top && sheet.offsetTop <= bottom) draw(view, sheet);
}

async function draw(view, sheet) {
  const mark = String(view.mark);
  if (!view.open || !view.doc || sheet.dataset.drawn === mark || sheet.dataset.drawing === mark) return;
  sheet.dataset.drawing = mark;
  let page = null;
  try {
    page = await view.doc.getPage(Number(sheet.dataset.page));
    if (!drawing(view, sheet, mark)) return;
    const task = paint(sheet, page);
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

function paint(sheet, page) {
  const natural = page.getViewport({ scale: 1 });
  const ratio = natural.width / natural.height;
  if (Math.abs(parseFloat(sheet.style.aspectRatio) - ratio) > 0.01) sheet.style.aspectRatio = String(ratio);
  const width = sheet.clientWidth;
  if (!width) return null;
  const viewport = page.getViewport({ scale: width / natural.width });
  const canvas = sheet.querySelector("canvas");
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.max(1, Math.floor(viewport.width * dpr));
  canvas.height = Math.max(1, Math.floor(viewport.height * dpr));
  const context = canvas.getContext("2d", { alpha: false });
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, viewport.width, viewport.height);
  return page.render({ canvasContext: context, viewport });
}

function drawing(view, sheet, mark) { return view.open && sheet.dataset.drawing === mark; }

function current(view, slot) { return view.open && slot.dataset.key === view.id; }

function fail(slot, text) { slot.replaceChildren(el("p", { class: "quiet", text })); }
