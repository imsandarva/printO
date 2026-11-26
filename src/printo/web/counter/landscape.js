/* Landscape 2-up mode: two portrait pages side-by-side on one A4 landscape sheet.
   This module owns the button, the preview rendering, and the state flag.
   It is a sibling of rotate.js — same dock, right beside the rotate button. */

import { el } from "./dom.js";
import { landscapeIcon } from "./icons.js";

/* ─── Button ─── */

export function createLandscapeButton(hooks) {
  const btn = el("button", {
    class: "landscape-btn",
    attrs: { type: "button", "aria-label": "2-up landscape", title: "Print two pages per sheet (L)" },
    on: {
      click: (event) => {
        event.stopPropagation();
        if (btn.disabled) return;
        hooks.onToggle?.();
      },
    },
  });
  btn.append(landscapeIcon());
  return btn;
}

export function syncLandscapeButton(btn, state) {
  if (!btn) return;
  btn.disabled = Boolean(state.busy);
  btn.classList.toggle("is-active", Boolean(state.landscape));
  btn.setAttribute("aria-pressed", state.landscape ? "true" : "false");
  const label = state.landscape ? "Exit 2-up landscape" : "2-up landscape — two pages per sheet";
  btn.setAttribute("aria-label", label);
  btn.setAttribute("title", (state.landscape ? "Exit 2-up" : "2-up per sheet") + " (L)");
}

/* ─── 2-up canvas composer ───
   Given two PDF page objects (left and right), paints them side-by-side
   onto a single landscape-shaped canvas filling the given frame.
   Returns the pdfjs render task (or null if inputs are invalid). */

export function paintLandscapeSheet(canvas, frame, leftPage, rightPage, leftRot, rightRot) {
  if (!canvas || !frame || !leftPage) return null;

  const dpr = pixels();
  // Landscape A4: width is the long side. Each half gets half the width.
  const halfW = frame.width / 2;
  const halfH = frame.height;

  canvas.width  = Math.max(1, Math.floor(frame.width  * dpr));
  canvas.height = Math.max(1, Math.floor(frame.height * dpr));
  canvas.dataset.landscape = "1";

  const ctx = canvas.getContext("2d", { alpha: false });
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Render each half independently to an offscreen canvas, then composite.
  const leftTask  = renderHalf(leftPage,  leftRot,  halfW, halfH, dpr);
  const rightTask = rightPage ? renderHalf(rightPage, rightRot, halfW, halfH, dpr) : null;

  const promise = Promise.all([leftTask.promise, rightTask?.promise ?? Promise.resolve()]).then(() => {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // Left half
    ctx.drawImage(leftTask.canvas, 0, 0, halfW, halfH);
    // Subtle divider line between pages
    ctx.strokeStyle = "rgba(26,23,20,0.08)";
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(halfW, 4);
    ctx.lineTo(halfW, halfH - 4);
    ctx.stroke();
    // Right half (may be blank if only one page)
    if (rightTask) ctx.drawImage(rightTask.canvas, halfW, 0, halfW, halfH);
  });

  return { promise, cancel: () => { leftTask?.cancel?.(); rightTask?.cancel?.(); } };
}

function renderHalf(page, extraRot, halfW, halfH, dpr) {
  const rotation = ((page.rotate || 0) + (extraRot || 0)) % 360;
  const natural  = page.getViewport({ scale: 1, rotation });
  const scale    = Math.min(halfW / natural.width, halfH / natural.height);
  const viewport = page.getViewport({ scale, rotation });

  const off = document.createElement("canvas");
  off.width  = Math.max(1, Math.floor(halfW * dpr));
  off.height = Math.max(1, Math.floor(halfH * dpr));

  const offCtx = off.getContext("2d", { alpha: false });
  offCtx.fillStyle = "#ffffff";
  offCtx.fillRect(0, 0, off.width, off.height);

  // Centre the page in its half
  const dx = (halfW - viewport.width)  / 2;
  const dy = (halfH - viewport.height) / 2;
  const transform = [dpr, 0, 0, dpr, dx * dpr, dy * dpr];

  const task = page.render({ canvasContext: offCtx, viewport, transform });
  return { canvas: off, promise: task.promise, cancel: task.cancel?.bind(task) };
}

function pixels() { return Math.min(window.devicePixelRatio || 1, 2); }

/* ─── Pair builder ───
   Given a flat list of page numbers being printed, return an array of
   [leftPageNum, rightPageNum | null] pairs for 2-up layout. */
export function landscapePairs(pageNums) {
  const pairs = [];
  for (let i = 0; i < pageNums.length; i += 2)
    pairs.push([pageNums[i], pageNums[i + 1] ?? null]);
  return pairs;
}
