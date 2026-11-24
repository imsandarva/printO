/* How large the page sits on the sheet.
   100 is the normal fit. Up to 125 the page grows, and anything past the paper is cut off.
   40 is the smallest that still reads clearly.
   Dragging follows the pointer. Arrow keys move one percent. The number that settles is the size that prints. */

import { el } from "./dom.js";

export const MIN_FIT = 40;
export const MAX_FIT = 125;

export function clampFit(value) {
  const number = Math.round(Number(value));
  if (!Number.isFinite(number)) return 100;
  return Math.min(MAX_FIT, Math.max(MIN_FIT, number));
}

export function sizeControl(value, onInput) {
  const row = el("div", { class: "fit" });
  const input = range(clampFit(value));
  const read = el("span", { class: "fit-read", attrs: { "aria-hidden": "true" } });
  const emit = (exact, settle) => publish(input, read, exact, settle, onInput);
  show(input, read, Number(input.value), clampFit(input.value));
  input.addEventListener("input", () => emit(input.value, false));
  input.addEventListener("change", () => emit(input.value, true));
  input.addEventListener("keydown", (event) => onKey(event, input, emit));
  row.append(input, read);
  return row;
}

function range(value) {
  const input = document.createElement("input");
  input.type = "range";
  input.min = String(MIN_FIT);
  input.max = String(MAX_FIT);
  input.step = "any";
  input.value = String(value);
  input.setAttribute("aria-label", "Size on the page");
  return input;
}

function publish(input, read, exact, settle, onInput) {
  const shown = clampFit(exact);
  const fit = settle ? shown : hold(exact);
  if (settle) input.value = String(shown);
  show(input, read, fit, shown);
  onInput(fit, shown);
}

function onKey(event, input, emit) {
  const next = step(clampFit(input.value), event.key);
  if (next == null) return;
  event.preventDefault();
  input.value = String(next);
  emit(next, true);
}

function step(fit, key) {
  if (key === "ArrowRight" || key === "ArrowUp" || key === "PageUp") return Math.min(MAX_FIT, fit + 1);
  if (key === "ArrowLeft" || key === "ArrowDown" || key === "PageDown") return Math.max(MIN_FIT, fit - 1);
  if (key === "Home") return MIN_FIT;
  if (key === "End") return MAX_FIT;
  return null;
}

function show(input, read, exact, shown) {
  const fill = ((exact - MIN_FIT) / (MAX_FIT - MIN_FIT)) * 100;
  input.style.setProperty("--fill", fill.toFixed(3) + "%");
  const label = shown + "%";
  if (read.textContent !== label) read.textContent = label;
  if (input.getAttribute("aria-valuetext") !== label) input.setAttribute("aria-valuetext", label);
}

function hold(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 100;
  return Math.min(MAX_FIT, Math.max(MIN_FIT, number));
}
