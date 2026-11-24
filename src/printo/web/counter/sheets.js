/* The sheet on the desk. Drawn here, so the browser's PDF window never frames it.
   The phone keeps the viewer; this page uses that same copy. */

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
  };
  live = view;
  read(view, slot, bytes);
}

function shutdown(view) {
  view.open = false;
  view.hold?.close();
  view.observer?.disconnect();
  view.resize?.disconnect();
  cancel(view);
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
  for (let number = 1; number <= view.doc.numPages; number += 1) stack.append(blank(number, ratio));
  scroller.append(stack);
  if (!current(view, slot)) return;
  const held = holdPages(scroller);
  const preview = column(held.frame, ratio, view);
  if (!current(view, slot)) { held.close(); return; }
  view.hold = held;
  view.root = preview;
  slot.replaceChildren(preview);
  matchPaper(view, scroller);
  if (!view.open) return;
  listen(view, scroller, stack);
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
  for (const sheet of stack.children) { sheet.dataset.drawn = ""; sheet.dataset.drawing = ""; }
  drawVisible(view, scroller, stack);
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
