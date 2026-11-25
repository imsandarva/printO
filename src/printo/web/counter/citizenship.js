/* Citizenship: two files become one sheet. The motion here is the whole interaction. */

import { el } from "./dom.js";

const TYPE_MS = 34;
const GLOW_MS = 2000;
const PAIR_NAME = /^Citizenship_\d+\.pdf$/;

export function isPairName(name) {
  return PAIR_NAME.test(name || "");
}

export function paintBar(root, model) {
  if (!root) return;
  const mode = model.pairing ? "on" : "off";
  if (root.dataset.mode !== mode) {
    root.dataset.mode = mode;
    root.replaceChildren(model.pairing ? live(model) : idle(model));
  }
  if (!model.pairing) return;
  const done = root.querySelector(".done");
  const cancel = root.querySelector(".cancel");
  if (!done || !cancel) return;
  const ready = model.count === 2 && !model.busy;
  done.disabled = !ready;
  cancel.disabled = Boolean(model.busy);
}

export function paintProcessing(on) {
  let node = document.getElementById("processing");
  if (!on) {
    if (node) node.remove();
    return;
  }
  if (node) return;
  node = el("div", { class: "veil processing", attrs: { id: "processing", role: "status", "aria-live": "polite" } });
  const card = el("div", { class: "processing-card" });
  card.append(el("span", { class: "spin", attrs: { "aria-hidden": "true" } }), el("p", { text: "Processing" }));
  node.append(card);
  document.body.append(node);
}

// Show the overlay only when the work actually takes a moment, and never as a flicker.
export function holdProcessing(paint) {
  let visible = false;
  let at = 0;
  const timer = window.setTimeout(() => {
    visible = true;
    at = performance.now();
    paint(true);
  }, 160);
  return function release() {
    window.clearTimeout(timer);
    if (!visible) {
      paint(false);
      return Promise.resolve();
    }
    const wait = Math.max(0, 480 - (performance.now() - at));
    return new Promise((resolve) => window.setTimeout(() => { paint(false); resolve(); }, wait));
  };
}

// Types the name, then lets the row glow. Returns a way to stop it if the file goes away.
export function playName(born, draw, done) {
  let timer = 0;
  let stopped = false;
  const stop = () => { stopped = true; window.clearTimeout(timer); };
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced) {
    born.shown = born.name;
    born.glow = true;
    born.glowAt = performance.now();
    draw();
    timer = window.setTimeout(() => { if (!stopped) done(); }, GLOW_MS);
    return stop;
  }
  let index = 0;
  const type = () => {
    if (stopped) return;
    index += 1;
    born.shown = born.name.slice(0, index);
    draw();
    if (index < born.name.length) timer = window.setTimeout(type, TYPE_MS + (index % 5 === 0 ? 24 : 0));
    else timer = window.setTimeout(glow, 180);
  };
  const glow = () => {
    if (stopped) return;
    born.glow = true;
    born.glowAt = performance.now();
    draw();
    timer = window.setTimeout(() => { if (!stopped) done(); }, GLOW_MS);
  };
  timer = window.setTimeout(type, 320);
  return stop;
}

function idle(model) {
  return el("button", {
    class: "citizenship",
    text: "Citizenship",
    attrs: { "aria-pressed": "false" },
    on: { click: model.onStart },
  });
}

function live(model) {
  const row = el("div", { class: "pair-live" });
  const ready = model.count === 2 && !model.busy;
  row.append(
    el("button", { class: "pill cancel", text: "Cancel", disabled: model.busy, on: { click: model.onCancel } }),
    el("button", {
      class: "pill done",
      text: "Done",
      disabled: !ready,
      attrs: { "aria-disabled": ready ? "false" : "true" },
      on: { click: model.onDone },
    }),
  );
  return row;
}
