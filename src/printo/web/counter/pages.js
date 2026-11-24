/* Which pages to print. One choice: all, even, odd, or a from–to range.
   Page numbers start at 1. The fields never keep a 0 or a page past the end.
   The tally belongs to the choice that is checked: it sits under that row,
   and under From–To while a custom range is open. It keeps the previous
   count for one beat when the choice changes, so the line can leave and arrive.
   pageNumbers is the same set the preview shows and the printer receives. */

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

export function pageNumbers(draft) {
  const count = atLeastOne(draft.count);
  if (draft.choice === "odd") return stepped(count, 1);
  if (draft.choice === "even") return stepped(count, 2);
  if (draft.choice !== "custom") return ranged(1, count);
  const start = Math.min(clampPage(draft.from, count), clampPage(draft.to, count));
  const end = Math.max(clampPage(draft.from, count), clampPage(draft.to, count));
  return ranged(start, end);
}

export function clampPage(value, pageCount) {
  const count = atLeastOne(pageCount);
  const number = Math.trunc(Number(value));
  if (!Number.isFinite(number) || number < 1) return 1;
  return Math.min(number, count);
}

export function paintPages(draft, job, hooks) {
  draft.count = atLeastOne(job.page_count || draft.count);
  const previous = draft.anchor || "";
  const priorCount = draft.shownCount;
  const animate = moves(previous, draft.choice);
  const wrap = el("div", { class: "field pages" });
  const group = choices(draft, hooks, previous, priorCount, animate);
  const span = range(draft, hooks, previous, priorCount, animate);
  wrap.append(head(draft.count), group, span);
  settle(group, span, draft, previous, animate);
  remember(draft, printedPages(draft));
  draft.anchor = draft.choice;
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
  row.append(el("span", { text: "Pages", attrs: { id: "pages-label" } }), el("span", { class: "field-meta", text: count === 1 ? "1 page" : count + " pages" }));
  return row;
}

function moves(previous, choice) {
  return Boolean(previous) && previous !== choice && motionOk();
}

function tallyNode(count, live, shift) {
  const node = el("p", {
    class: shift ? "page-tally shift" : "page-tally",
    attrs: live ? { id: "pages-tally", "aria-live": "polite", "aria-atomic": "true" } : { "aria-hidden": "true" },
  });
  writeTally(node, count);
  return node;
}

function writeTally(node, count) {
  node.replaceChildren(el("span", { class: "page-count", text: String(count) }), el("span", { class: "page-rest", text: tallyRest(count) }));
}

function tallyRest(count) {
  return count === 1 ? " page in total" : " pages in total";
}

function refreshTally(draft) {
  const node = document.getElementById("pages-tally");
  if (!node) return;
  const count = printedPages(draft);
  if (node.textContent === pagesInTotal(count)) { remember(draft, count); return; }
  writeTally(node, count);
  remember(draft, count);
  if (!motionOk()) return;
  // Drop the class and force layout so the same line can settle again.
  node.classList.remove("shift");
  void node.offsetWidth;
  node.classList.add("shift");
}

function remember(draft, count) {
  draft.shownCount = count;
  draft.shown = pagesInTotal(count);
}

function motionOk() {
  return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function printedPages(draft) { return pageNumbers(draft).length; }

function stepped(count, first) {
  const pages = [];
  for (let number = first; number <= count; number += 2) pages.push(number);
  return pages;
}

function ranged(start, end) {
  const pages = [];
  for (let number = start; number <= end; number += 1) pages.push(number);
  return pages;
}

function pagesInTotal(count) {
  return String(count) + tallyRest(count);
}

function choices(draft, hooks, previous, priorCount, animate) {
  const group = el("div", { class: "page-choices", attrs: { role: "radiogroup", "aria-labelledby": "pages-label", "aria-describedby": "pages-tally" } });
  group.append(...CHOICES.map((item) => option(item, draft, hooks, previous, priorCount, animate)));
  return group;
}

function option(item, draft, hooks, previous, priorCount, animate) {
  const row = el("div", { class: "page-option", attrs: { "data-choice": item.id } });
  row.append(choiceButton(item, draft, hooks));
  if (item.id !== "custom") row.append(choiceNote(item.id, draft, previous, priorCount, animate));
  return row;
}

/* open: already under the checked row. arrive: about to open there.
   leave: still under the row that was checked, holding the old count. shut: no line. */
function choiceNote(id, draft, previous, priorCount, animate) {
  const mode = noteMode(id, draft.choice, previous, animate);
  const open = mode === "open" || mode === "leave";
  const live = mode === "open" || mode === "arrive";
  const slot = el("div", { class: open ? "page-note open" : "page-note", attrs: live ? null : { "aria-hidden": "true" } });
  const clip = el("div", { class: "page-note-clip" });
  if (mode !== "shut") clip.append(tallyNode(noteCount(mode, draft, priorCount), live, mode === "open" && countChanged(priorCount, draft)));
  slot.append(clip);
  return slot;
}

function noteMode(id, choice, previous, animate) {
  if (id === choice) return animate ? "arrive" : "open";
  if (animate && id === previous) return "leave";
  return "shut";
}

function noteCount(mode, draft, priorCount) {
  if (mode === "leave" && priorCount != null) return priorCount;
  return printedPages(draft);
}

function countChanged(priorCount, draft) {
  return priorCount != null && priorCount !== printedPages(draft) && motionOk();
}

function settle(group, span, draft, previous, animate) {
  if (!animate) { if (draft.choice === "custom") holdRange(span, true); return; }
  // Start from the row the line is leaving, then let the two heights trade places.
  if (previous === "custom") { span.classList.add("open"); const clip = span.querySelector(".page-span-clip"); if (clip) clip.inert = true; }
  const leave = noteOf(group, previous);
  const arrive = noteOf(group, draft.choice);
  glide(() => {
    if (!span.isConnected) return;
    if (leave) leave.classList.remove("open");
    if (arrive) arrive.classList.add("open");
    holdRange(span, draft.choice === "custom");
  });
}

function noteOf(group, id) {
  return group.querySelector('.page-option[data-choice="' + id + '"] .page-note');
}

function glide(flip) {
  requestAnimationFrame(() => { void document.body.offsetHeight; flip(); });
}

function holdRange(span, open) {
  const clip = span.querySelector(".page-span-clip");
  span.classList.toggle("open", open);
  if (clip) clip.inert = !open;
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

function range(draft, hooks, previous, priorCount, animate) {
  const span = el("div", { class: "page-span" });
  const clip = el("div", { class: "page-span-clip" });
  const closing = animate && previous === "custom";
  if (draft.choice !== "custom" || animate) clip.inert = true;
  const row = el("div", { class: "page-range" });
  row.append(bound(draft, hooks, "from", "From", "page-from"), bound(draft, hooks, "to", "To", "page-to"));
  clip.append(row);
  if (draft.choice === "custom") clip.append(tallyNode(printedPages(draft), true, !animate && countChanged(priorCount, draft)));
  else if (closing) clip.append(tallyNode(priorCount != null ? priorCount : printedPages(draft), false, false));
  span.append(clip);
  return span;
}

function bound(draft, hooks, which, label, id) {
  const wrap = el("label", { class: "bound" });
  const input = document.createElement("input");
  input.id = id;
  input.type = "text";
  input.inputMode = "numeric";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.maxLength = String(draft.count).length;
  input.value = String(draft[which]);
  input.addEventListener("input", () => onType(draft, hooks, which, input));
  input.addEventListener("blur", () => onBlur(draft, hooks, which));
  wrap.append(el("span", { text: label }), input);
  return wrap;
}

function onType(draft, hooks, which, input) {
  const live = liveBound(input.value, draft.count);
  if (input.value !== live.text) input.value = live.text;
  if (live.value == null || draft[which] === live.value) return;
  draft[which] = live.value;
  draft.dirty = true;
  refreshTally(draft);
  hooks.onRange?.();
}

function onBlur(draft, hooks, which) {
  const id = which === "from" ? "page-from" : "page-to";
  draft[which] = typedOrKept(draft[which], id, draft.count);
  // Keep the number just entered, and move the other end so the range stays in order.
  if (draft.from > draft.to) draft[which === "from" ? "to" : "from"] = draft[which];
  draft.pages = writePages(draft);
  draft.dirty = true;
  showRange(draft);
  refreshTally(draft);
  hooks.onRange?.();
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

