/* Which pages to print. One choice: all, even, odd, or a from–to range.
   Page numbers start at 1. The fields never keep a 0 or a page past the end. */

import { el } from "./dom.js";
import { checkIcon } from "./icons.js";

const CHOICES = [
  { id: "all", label: "All" },
  { id: "even", label: "Even pages only" },
  { id: "odd", label: "Odd pages only" },
  { id: "custom", label: "Custom" },
];

export function readPages(spec, pageCount) {
  const count = atLeastOne(pageCount);
  const text = String(spec || "all").trim().toLowerCase();
  if (text === "odd" || text === "even") return { choice: text, from: 1, to: count, count };
  const span = /^(\d+)\s*-\s*(\d+)$/.exec(text);
  if (span) return custom(span[1], span[2], count);
  if (/^\d+$/.test(text)) return custom(text, text, count);
  return { choice: "all", from: 1, to: count, count };
}

export function writePages(draft) {
  if (draft.choice === "even") return "even";
  if (draft.choice === "odd") return "odd";
  if (draft.choice !== "custom") return "all";
  const count = atLeastOne(draft.count);
  const start = Math.min(clampPage(draft.from, count), clampPage(draft.to, count));
  const end = Math.max(clampPage(draft.from, count), clampPage(draft.to, count));
  return start === end ? String(start) : start + "-" + end;
}

export function clampPage(value, pageCount) {
  const count = atLeastOne(pageCount);
  const number = Math.trunc(Number(value));
  if (!Number.isFinite(number) || number < 1) return 1;
  return Math.min(number, count);
}

export function paintPages(draft, job, hooks) {
  draft.count = atLeastOne(job.page_count || draft.count);
  const wrap = el("div", { class: "field pages" });
  const span = range(draft);
  wrap.append(head(draft.count), choices(draft, hooks), span);
  reveal(span, draft, hooks.wasOpen);
  return wrap;
}

function custom(from, to, count) {
  const start = clampPage(from, count);
  const end = clampPage(to, count);
  return { choice: "custom", from: Math.min(start, end), to: Math.max(start, end), count };
}

function atLeastOne(pageCount) {
  const count = Math.trunc(Number(pageCount));
  return Number.isFinite(count) && count > 0 ? count : 1;
}

function head(count) {
  const row = el("div", { class: "field-head" });
  const title = el("span", { text: "Pages", attrs: { id: "pages-label" } });
  row.append(title, el("span", { class: "field-meta", text: count === 1 ? "1 page" : count + " pages" }));
  return row;
}

function choices(draft, hooks) {
  const group = el("div", { class: "page-choices", attrs: { role: "radiogroup", "aria-labelledby": "pages-label" } });
  group.append(...CHOICES.map((item) => choiceButton(item, draft, hooks)));
  return group;
}

function choiceButton(item, draft, hooks) {
  const on = draft.choice === item.id;
  const button = el("button", {
    class: "page-choice",
    attrs: { id: "page-" + item.id, role: "radio", "aria-checked": on ? "true" : "false", tabindex: on ? "0" : "-1" },
    on: { click: () => pick(draft, item.id, hooks), keydown: (event) => onChoiceKey(event, draft, item.id, hooks) },
  });
  const mark = el("span", { class: "page-mark", attrs: { "aria-hidden": "true" } });
  mark.append(checkIcon());
  button.append(mark, el("span", { class: "page-name", text: item.label }));
  return button;
}

function pick(draft, choice, hooks) {
  if (draft.choice === choice) return;
  draft.choice = choice;
  draft.dirty = true;
  draft.pages = writePages(draft);
  draft.focus = choice === "custom" ? "page-from" : "page-" + choice;
  hooks.onChange();
}

function onChoiceKey(event, draft, id, hooks) {
  const next = arrowChoice(id, event.key);
  if (!next) return;
  event.preventDefault();
  pick(draft, next, hooks);
}

function arrowChoice(id, key) {
  const index = CHOICES.findIndex((item) => item.id === id);
  if (key === "ArrowDown" || key === "ArrowRight") return CHOICES[(index + 1) % CHOICES.length].id;
  if (key === "ArrowUp" || key === "ArrowLeft") return CHOICES[(index + CHOICES.length - 1) % CHOICES.length].id;
  if (key === "Home") return CHOICES[0].id;
  if (key === "End") return CHOICES[CHOICES.length - 1].id;
  return "";
}

function range(draft) {
  const span = el("div", { class: "page-span" });
  const clip = el("div", { class: "page-span-clip" });
  if (draft.choice !== "custom") clip.inert = true;
  const row = el("div", { class: "page-range" });
  row.append(bound(draft, "from", "From", "page-from"), bound(draft, "to", "To", "page-to"));
  clip.append(row);
  span.append(clip);
  return span;
}

function bound(draft, which, label, id) {
  const wrap = el("label", { class: "bound" });
  const input = document.createElement("input");
  input.id = id;
  input.type = "text";
  input.inputMode = "numeric";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.maxLength = String(draft.count).length;
  input.value = String(draft[which]);
  input.addEventListener("input", () => onType(draft, which, input));
  input.addEventListener("blur", () => onBlur(draft, which));
  wrap.append(el("span", { text: label }), input);
  return wrap;
}

function onType(draft, which, input) {
  const live = liveBound(input.value, draft.count);
  if (input.value !== live.text) input.value = live.text;
  if (live.value == null || draft[which] === live.value) return;
  draft[which] = live.value;
  draft.dirty = true;
}

function onBlur(draft, which) {
  const id = which === "from" ? "page-from" : "page-to";
  draft[which] = typedOrKept(draft[which], id, draft.count);
  // Keep the number just entered, and move the other end so the range stays in order.
  if (draft.from > draft.to) draft[which === "from" ? "to" : "from"] = draft[which];
  draft.pages = writePages(draft);
  draft.dirty = true;
  showRange(draft);
}

function typedOrKept(kept, id, count) {
  const input = document.getElementById(id);
  const live = liveBound(input ? input.value : "", count);
  return live.value == null ? clampPage(kept, count) : live.value;
}

function liveBound(raw, pageCount) {
  const count = atLeastOne(pageCount);
  const text = String(raw || "").replace(/\D/g, "").slice(0, String(count).length);
  if (!text) return { text: "", value: null };
  const number = Number(text);
  if (number < 1) return { text: "1", value: 1 };
  if (number > count) return { text: String(count), value: count };
  return { text: String(number), value: number };
}

function showRange(draft) {
  const from = document.getElementById("page-from");
  const to = document.getElementById("page-to");
  if (from) from.value = String(draft.from);
  if (to) to.value = String(draft.to);
}

function reveal(span, draft, wasOpen) {
  if (draft.choice !== "custom") return;
  const clip = span.querySelector(".page-span-clip");
  const open = () => { span.classList.add("open"); if (clip) clip.inert = false; };
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (wasOpen || reduce) open();
  else requestAnimationFrame(open);
}
