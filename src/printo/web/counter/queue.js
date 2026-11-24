/* The file list: a year, then its months, then its days. Opening one only flips that section. */

import { arrange, isOpen, whenLabel } from "./dates.js";
import { el } from "./dom.js";
import { checkIcon } from "./icons.js";

export function paintQueue(root, model) {
  if (!root) return;
  const now = new Date();
  const top = root.scrollTop;
  const focusId = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.fold || "" : "";
  const years = arrange(model.jobs, now, model.waiting !== false);
  root.replaceChildren(...years.map((year) => year.key === "unknown" ? other(year, model, now) : section(year, model, now)));
  root.scrollTop = top;
  if (!focusId) return;
  const next = root.querySelector('[data-fold="' + CSS.escape(focusId) + '"]');
  if (next) next.focus();
}

export function setOpen(root, id, open) {
  if (!root) return false;
  const node = root.querySelector('[data-node="' + CSS.escape(id) + '"]');
  if (!node) return false;
  node.dataset.open = open ? "true" : "false";
  const button = node.firstElementChild;
  const clip = button && button.nextElementSibling && button.nextElementSibling.firstElementChild;
  if (button) button.setAttribute("aria-expanded", open ? "true" : "false");
  if (clip) clip.inert = !open;
  return true;
}

function section(node, model, now) {
  const open = isOpen(node.kind, node.key, model.folds, now);
  const inner = node.jobs ? node.jobs.map((job) => card(job, model, now)) : node.children.map((child) => section(child, model, now));
  return block(node, model, open, inner);
}

function other(year, model, now) {
  const jobs = year.children.flatMap((month) => month.children.flatMap((day) => day.jobs));
  const open = isOpen(year.kind, year.key, model.folds, now);
  return block(year, model, open, jobs.map((job) => card(job, model, now)));
}

function block(node, model, open, inner) {
  const sectionNode = el("section", { class: "node " + node.kind + (node.today ? " today" : "") });
  sectionNode.dataset.node = node.id;
  sectionNode.dataset.open = open ? "true" : "false";
  if (node.waiting) sectionNode.dataset.waiting = "true";
  const body = el("div", { class: "fold-body" });
  const clip = el("div", { class: "fold-clip" });
  if (!open) clip.inert = true;
  clip.append(...inner);
  body.append(clip);
  sectionNode.append(header(node, model, open), body);
  return sectionNode;
}

function header(node, model, open) {
  const button = el("button", {
    class: "fold",
    attrs: { "data-fold": node.id, "aria-expanded": open ? "true" : "false", "aria-label": spoken(node) },
    on: { click: () => model.onToggle(node.id, button.getAttribute("aria-expanded") === "true") },
  });
  button.append(chevron(), title(node));
  const aside = el("span", { class: "fold-aside" });
  if (node.waiting) aside.append(el("i", { class: "wait-dot", attrs: { "aria-hidden": "true" } }));
  aside.append(el("span", { class: "fold-count", text: String(node.total) }));
  button.append(aside);
  return button;
}

function title(node) {
  const row = el("span", { class: "fold-title" });
  if (node.dayNum) row.append(el("span", { class: "day-num", text: node.dayNum }));
  row.append(el("span", { class: node.kind === "day" ? "day-name" : "fold-name", text: node.title }));
  return row;
}

function spoken(node) {
  const files = node.total === 1 ? "1 file" : node.total + " files";
  const waiting = node.waiting === 0 ? "" : node.waiting === 1 ? ", 1 still waiting" : ", " + node.waiting + " still waiting";
  return node.spoken + ", " + files + waiting;
}

function card(job, model, now) {
  const picking = Boolean(model.picking);
  const picks = model.picks;
  const on = picking ? Boolean(picks && picks.has(job.id)) : job.id === model.selected;
  const classes = ["card", picking ? "picking" : "", on ? "on" : "", !picking && model.fresh(job.id) ? "fresh" : ""].filter(Boolean).join(" ");
  const button = el("button", {
    class: classes,
    attrs: { "aria-pressed": on ? "true" : "false" },
    on: { click: () => model.onSelect(job.id) },
  });
  const body = el("div", { class: "card-body" });
  const top = el("div", { class: "card-top" });
  top.append(
    el("span", { class: "num", text: job.name || "Untitled", attrs: { title: job.name || "" } }),
    el("span", { class: "when", text: whenLabel(job.created_at, now) }),
  );
  body.append(top, el("span", { class: "label", text: job.label || "", attrs: { "data-status": job.status || "" } }));
  if (picking) button.append(tick(on));
  button.append(body);
  return button;
}

function tick(on) {
  const mark = el("span", { class: on ? "tick on" : "tick", attrs: { "aria-hidden": "true" } });
  if (on) mark.append(checkIcon());
  return mark;
}

function chevron() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("chev");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M6 3.5 11 8 6 12.5");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.6");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  svg.append(path);
  return svg;
}
