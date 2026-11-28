/* Landscape 2-up mode: two portrait pages side-by-side on one A4 landscape sheet.
   This module owns the button, the preview rendering, and the state flag.
   It is a sibling of rotate.js — same dock, right beside the rotate button. */

import { el } from "./dom.js";
import { landscapeIcon } from "./icons.js";
import { blitPage, prepareSheet } from "./proxy.js";

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

/* Two pictures already drawn, placed side by side. Nothing is rendered from the file here. */

export function paintLandscapeSheet(canvas, frame, left, right, leftRot, rightRot) {
  if (!canvas || !frame || !left) return;
  const ctx = prepareSheet(canvas, frame);
  const halfW = frame.width / 2;
  const cell = { width: halfW, height: frame.height };
  blitPage(ctx, { ...cell, x: 0, y: 0 }, left, leftRot);
  if (right) blitPage(ctx, { ...cell, x: halfW, y: 0 }, right, rightRot);
  ctx.strokeStyle = "rgba(26,23,20,0.08)";
  ctx.lineWidth = 0.5;
  ctx.beginPath();
  ctx.moveTo(halfW, 4);
  ctx.lineTo(halfW, frame.height - 4);
  ctx.stroke();
  canvas.dataset.landscape = "1";
  canvas.dataset.rot = String(((Number(leftRot) || 0) % 360 + 360) % 360);
}

/* ─── Pair builder ───
   Given a flat list of page numbers being printed, return an array of
   [leftPageNum, rightPageNum | null] pairs for 2-up layout. */
export function landscapePairs(pageNums) {
  const pairs = [];
  for (let i = 0; i < pageNums.length; i += 2)
    pairs.push([pageNums[i], pageNums[i + 1] ?? null]);
  return pairs;
}
