/* A layer over the list. Closing it puts the customer back on the same scroll, with the same files. */

import { loadPdf } from "./documents.js";
import { el } from "./dom.js";
import { fill, sizeLabel, typeName } from "./format.js";
import { trackImage } from "./gestures.js";
import { closeIcon, fileIcon, minusIcon, plusIcon } from "./icons.js";

let current = null;

export function openViewer(item, session) {
  closeViewer();
  if (!item.ok) { openInfo(item, session.copy, "blocked"); return; }
  if (item.kind === "image") { openPhoto(item, session.items.filter((entry) => entry.ok && entry.kind === "image"), session.copy); return; }
  if (item.kind === "pdf") { openPdf(item, session.copy); return; }
  openInfo(item, session.copy, "doc");
}

function closeViewer() {
  if (!current) return;
  const open = current;
  current = null;
  open.closed = true;
  open.root.remove();
  document.body.classList.remove("locked");
  document.removeEventListener("keydown", open.onKey);
  if (open.stop) open.stop();
  for (const task of open.tasks) task.cancel?.();
  if (open.doc) open.doc.destroy();
  if (open.focus && document.contains(open.focus)) open.focus.focus();
}

function mount(className, label) {
  const focus = document.activeElement;
  const root = el("div", { class: "viewer " + className, attrs: { role: "dialog", "aria-modal": "true", "aria-label": label } });
  document.body.append(root);
  document.body.classList.add("locked");
  const onKey = (event) => { if (event.key === "Escape") closeViewer(); };
  document.addEventListener("keydown", onKey);
  current = { root, onKey, focus, closed: false, tasks: [], doc: null, stop: null };
  return root;
}

function bar(copy, title, trailing) {
  const header = el("div", { class: "viewer-bar" });
  const close = el("button", { class: "close", attrs: { "aria-label": copy.close } });
  close.append(closeIcon());
  close.addEventListener("click", closeViewer);
  const name = el("p", { class: "viewer-name", text: title });
  header.append(close, name, trailing || el("span", { class: "bar-spacer", attrs: { "aria-hidden": "true" } }));
  close.focus();
  return { header, name };
}

function openPhoto(item, images, copy) {
  let index = Math.max(0, images.findIndex((entry) => entry.id === item.id));
  const root = mount("photo", item.name);
  const { header, name } = bar(copy, item.name);
  const stage = el("div", { class: "stage" });
  const img = el("img", { class: "frame", attrs: { alt: "", draggable: "false" } });
  stage.append(img);
  root.append(header, stage);
  current.stop = trackImage(stage, img, { onSwipe: (direction) => show(index + direction) });
  img.addEventListener("error", () => failPhoto(stage, img, copy));
  img.addEventListener("load", () => { img.hidden = false; const note = stage.querySelector(".viewer-note"); if (note) note.remove(); });
  show(index);

  function show(next) {
    if (!images.length || !current || current.root !== root) return;
    index = (next + images.length) % images.length;
    const entry = images[index];
    if (!entry.fullUrl) entry.fullUrl = URL.createObjectURL(entry.file);
    img.hidden = false;
    img.src = entry.fullUrl;
    name.textContent = images.length > 1 ? fill(copy.page, { current: index + 1, total: images.length }) : entry.name;
    root.setAttribute("aria-label", entry.name);
  }
}

function failPhoto(stage, img, copy) {
  img.hidden = true;
  if (stage.querySelector(".viewer-note")) return;
  stage.append(el("p", { class: "viewer-note", text: copy.preview_fail }));
}

async function openPdf(item, copy) {
  const root = mount("pages", item.name);
  const zoomOut = el("button", { class: "zoom", attrs: { "aria-label": copy.zoom_out } });
  const zoomIn = el("button", { class: "zoom", attrs: { "aria-label": copy.zoom_in } });
  zoomOut.append(minusIcon());
  zoomIn.append(plusIcon());
  const zooms = el("div", { class: "zooms" });
  zooms.append(zoomOut, zoomIn);
  const { header } = bar(copy, item.name, zooms);
  const scroller = el("div", { class: "scroller" });
  const stack = el("div", { class: "stack" });
  const opening = el("p", { class: "opening", text: copy.opening });
  const pager = el("p", { class: "pager" });
  stack.append(opening);
  scroller.append(stack);
  root.append(header, scroller, pager);
  let zoom = 1;
  let doc = null;
  try {
    doc = await loadPdf(item.file);
    if (!current || current.closed || current.root !== root) { doc.destroy(); return; }
    current.doc = doc;
    opening.remove();
    const first = await doc.getPage(1);
    const base = first.getViewport({ scale: 1 });
    first.cleanup();
  stack.style.setProperty("--ratio", String(base.width / base.height));
  for (let number = 1; number <= doc.numPages; number += 1) {
    const sheet = el("div", { class: "sheet" });
    sheet.dataset.page = String(number);
    sheet.append(el("canvas"));
    stack.append(sheet);
  }
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) if (entry.isIntersecting) draw(entry.target);
  }, { root: scroller, rootMargin: "700px 0px" });
  for (const sheet of stack.querySelectorAll(".sheet")) observer.observe(sheet);
  const previous = current.stop;
  current.stop = () => { observer.disconnect(); if (previous) previous(); };
  applyWidth();
  requestAnimationFrame(() => { applyWidth(); drawVisible(); updatePager(); });
  zoomOut.addEventListener("click", () => changeZoom(zoom / 1.35));
  zoomIn.addEventListener("click", () => changeZoom(zoom * 1.35));
  scroller.addEventListener("scroll", updatePager, { passive: true });
  scroller.addEventListener("wheel", (event) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    changeZoom(zoom * (event.deltaY < 0 ? 1.06 : 0.94));
  }, { passive: false });
  updatePager();

  function applyWidth() {
    stack.style.setProperty("--page-width", Math.max(160, (scroller.clientWidth - 28) * zoom) + "px");
    zoomOut.disabled = zoom <= 1.01;
    zoomIn.disabled = zoom >= 2.6;
  }

  function changeZoom(next) {
    zoom = Math.min(2.6, Math.max(1, next));
    for (const sheet of stack.querySelectorAll(".sheet")) sheet.dataset.drawn = "";
    applyWidth();
    requestAnimationFrame(drawVisible);
  }

  function drawVisible() {
    const top = scroller.scrollTop - 700;
    const bottom = scroller.scrollTop + scroller.clientHeight + 700;
    for (const sheet of stack.querySelectorAll(".sheet")) {
      if (sheet.offsetTop + sheet.offsetHeight >= top && sheet.offsetTop <= bottom) draw(sheet);
    }
  }

  async function draw(sheet) {
    if (!current || current.closed || current.doc !== doc) return;
    const mark = zoom.toFixed(3);
    if (sheet.dataset.drawn === mark || sheet.dataset.drawing === mark) return;
    sheet.dataset.drawing = mark;
    try {
      const page = await doc.getPage(Number(sheet.dataset.page));
      if (!current || current.closed || sheet.dataset.drawing !== zoom.toFixed(3)) { page.cleanup(); return; }
      const width = sheet.clientWidth || parseFloat(getComputedStyle(stack).getPropertyValue("--page-width"));
      const natural = page.getViewport({ scale: 1 });
      const viewport = page.getViewport({ scale: width / natural.width });
      const canvas = sheet.querySelector("canvas");
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.floor(viewport.width * dpr));
      canvas.height = Math.max(1, Math.floor(viewport.height * dpr));
      const context = canvas.getContext("2d", { alpha: false });
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, viewport.width, viewport.height);
      const task = page.render({ canvasContext: context, viewport });
      current.tasks.push(task);
      await task.promise;
      page.cleanup();
      sheet.dataset.drawn = zoom.toFixed(3);
    } catch {
      /* A cancelled draw, or a page that cannot be shown. The file can still be sent. */
    } finally {
      if (sheet.dataset.drawing === mark) sheet.dataset.drawing = "";
    }
  }

  function updatePager() {
    const sheets = [...stack.querySelectorAll(".sheet")];
    if (!sheets.length || !doc) return;
    const line = scroller.scrollTop + 28;
    let pageNumber = 1;
    for (const [index, sheet] of sheets.entries()) if (sheet.offsetTop <= line) pageNumber = index + 1;
    pager.textContent = fill(copy.page, { current: pageNumber, total: doc.numPages });
  }
  } catch {
    if (doc) { if (current && current.doc === doc) current.doc = null; doc.destroy(); }
    if (current && current.root === root) showPdfFailed(root, item, copy);
  }
}

function showPdfFailed(root, item, copy) {
  root.className = "viewer info";
  root.replaceChildren();
  fillInfo(root, item, copy, "failed");
}

function openInfo(item, copy, mode) {
  const root = mount("info", item.name);
  fillInfo(root, item, copy, mode);
}

function fillInfo(root, item, copy, mode) {
  const { header } = bar(copy, item.name);
  const body = el("div", { class: "info-body" });
  const glyph = el("div", { class: "glyph big" });
  glyph.append(fileIcon(), el("small", { text: typeName(item.ext) }));
  body.append(glyph, el("h2", { text: item.name }), el("p", { class: "meta", text: typeName(item.ext) + " · " + sizeLabel(item.file.size) }));
  if (mode === "blocked") body.append(el("p", { class: "reassure bad", text: item.error }));
  else {
    if (mode === "failed") body.append(el("p", { class: "reassure", text: copy.preview_fail }));
    body.append(el("p", { class: "reassure", text: copy.still_send }));
  }
  root.append(header, body);
}
