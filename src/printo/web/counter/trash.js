/* Trash is a place, not a button that throws a file away. The last question lives in the dialog. */

import { el } from "./dom.js";
import { backIcon, trashIcon } from "./icons.js";

export function paintBin(model) {
  paintHead(document.getElementById("rail-head"), model);
  paintFoot(document.getElementById("rail-foot"), model);
}

export function paintAsk(model) {
  const existing = document.getElementById("ask");
  if (!model.open) { if (existing) existing.remove(); return; }
  const busy = model.busy ? "1" : "0";
  if (existing && existing.dataset.key === model.body && existing.dataset.busy === busy) return;
  if (existing) existing.remove();
  const veil = el("div", { class: "veil", attrs: { id: "ask", role: "dialog", "aria-modal": "true", "aria-labelledby": "ask-title" } });
  veil.dataset.key = model.body;
  veil.dataset.busy = busy;
  const card = el("div", { class: "ask" });
  const actions = el("div", { class: "ask-actions" });
  const no = el("button", { class: "ask-no", text: "Cancel", disabled: model.busy, on: { click: model.onNo } });
  const yes = el("button", { class: "ask-yes", text: model.busy ? "Deleting…" : "Delete forever", disabled: model.busy, on: { click: model.onYes } });
  actions.append(no, yes);
  card.append(el("h2", { attrs: { id: "ask-title" }, text: "Delete forever?" }), el("p", { text: model.body }), actions);
  veil.append(card);
  veil.addEventListener("click", (event) => { if (event.target === veil && !model.busy) model.onNo(); });
  veil.addEventListener("keydown", (event) => trap(event, no, yes));
  document.body.append(veil);
  no.focus();
}

function paintHead(node, model) {
  if (!node) return;
  if (model.view !== "trash") {
    node.hidden = true;
    if (node.dataset.key) { node.dataset.key = ""; node.replaceChildren(); }
    return;
  }
  node.hidden = false;
  const side = model.picking ? (model.allOn ? "none" : "all") : (model.count ? "select" : "empty");
  const key = (model.picking ? "pick" : "look") + ":" + side;
  if (node.dataset.key === key) return;
  node.dataset.key = key;
  const left = model.picking
    ? el("button", { class: "rail-back", text: "Cancel", on: { click: model.onCancel } })
    : back(model.onClose);
  const right = model.picking
    ? el("button", { class: "rail-action", text: model.allOn ? "None" : "All", on: { click: model.onAll } })
    : model.count
      ? el("button", { class: "rail-action", text: "Select", on: { click: model.onPick } })
      : el("span", { class: "rail-side" });
  node.replaceChildren(left, el("h2", { class: "rail-title", text: "Trash" }), right);
}

function paintFoot(node, model) {
  if (!node) return;
  const picking = model.view === "trash" && model.picking;
  const show = model.view !== "trash" || picking;
  node.hidden = !show;
  if (!show) { node.dataset.key = ""; node.replaceChildren(); return; }
  const key = [model.view, picking ? model.pickCount : model.count, model.note || "", model.working].join("|");
  if (node.dataset.key === key) return;
  node.dataset.key = key;
  node.replaceChildren(picking ? pickBar(model) : entry(model));
}

function back(onClick) {
  const button = el("button", { class: "rail-back", attrs: { "aria-label": "Files" }, on: { click: onClick } });
  button.append(backIcon(), el("span", { text: "Files" }));
  return button;
}

function entry(model) {
  const button = el("button", {
    class: "trash-entry",
    attrs: { "aria-label": model.count ? "Trash, " + files(model.count) : "Trash" },
    on: { click: model.onOpen },
  });
  button.append(trashIcon(), el("span", { class: "trash-name", text: "Trash" }));
  if (model.count) button.append(el("span", { class: "count", text: String(model.count) }));
  return button;
}

function pickBar(model) {
  const bar = el("div", { class: "pick-bar" });
  const label = model.pickCount === 0 ? "Nothing selected" : model.pickCount === 1 ? "1 selected" : model.pickCount + " selected";
  const button = el("button", { class: "purge", disabled: !model.pickCount || Boolean(model.working), on: { click: model.onDelete } });
  button.append(trashIcon(), el("span", { text: "Delete" }));
  bar.append(el("span", { class: "pick-count", text: label }), button);
  if (model.note) bar.append(el("p", { class: "note pick-note", text: model.note }));
  return bar;
}

function files(count) { return count === 1 ? "1 file" : count + " files"; }

function trap(event, no, yes) {
  if (event.key !== "Tab") return;
  const items = [no, yes].filter((node) => !node.disabled);
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}
