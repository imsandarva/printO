/* The counter. The live stream is only a nudge; the job list is what we show.
   The preview is grey because this printer is black and white. */

import { el } from "./dom.js";
import { trashIcon } from "./icons.js";
import { clampPage, paintPages, readPages, writePages } from "./pages.js";
import { paintQueue, setOpen } from "./queue.js";
import { paintAsk, paintBin } from "./trash.js";

const COPY_LIMIT = 20;
const state = {
  jobs: [],
  seen: new Set(),
  fresh: new Map(),
  folds: { shut: new Set(), forced: new Set() },
  drafts: {},
  previews: {},
  selected: null,
  view: "files",
  trash: [],
  trashFolds: { shut: new Set(), forced: new Set() },
  picking: false,
  picks: new Set(),
  ask: false,
  printer: null,
  printerLost: false,
  offline: false,
  live: false,
  working: "",
  note: "",
  toast: "",
  undo: "",
};

function boot() {
  document.addEventListener("pointerdown", warmSound, { passive: true });
  document.addEventListener("keydown", onKey);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
  window.setInterval(renderQueue, 30000);
  window.setInterval(loadPrinter, 8000);
  loadPrinter();
  loadJobs();
  listen();
}

function refresh() { loadJobs(); loadPrinter(); }

function listen() {
  const source = new EventSource("/admin/events");
  source.addEventListener("ready", () => loadJobs());
  source.addEventListener("job", (event) => {
    try { onJob(JSON.parse(event.data)); }
    catch { loadJobs(); }
  });
}

async function loadJobs() {
  const announce = state.live;
  try {
    const [active, bin] = await Promise.all([readJSON("/admin/jobs"), readJSON("/admin/jobs?trashed=1")]);
    if (!active.ok || !Array.isArray(active.jobs) || !bin.ok || !Array.isArray(bin.jobs)) throw new Error("jobs");
    take(active.jobs, bin.jobs, announce);
    state.offline = false;
  } catch {
    state.offline = true;
  }
  state.live = true;
  render();
}

async function loadPrinter() {
  try {
    const body = await readJSON("/admin/printer");
    if (body.ok) { state.printer = body; state.printerLost = false; }
  } catch {
    state.printerLost = true;
  }
  renderPrinter();
}

function take(jobs, bin, announce) {
  const ids = new Set();
  let arrived = false;
  for (const job of jobs) {
    ids.add(job.id);
    if (!state.seen.has(job.id)) {
      state.seen.add(job.id);
      if (announce) { arrived = true; state.fresh.set(job.id, Date.now()); }
    }
  }
  for (const job of bin) { ids.add(job.id); state.seen.add(job.id); }
  for (const id of Array.from(state.seen)) if (!ids.has(id)) { state.seen.delete(id); forget(id); }
  state.jobs = jobs.slice();
  state.trash = bin.slice();
  for (const id of Array.from(state.picks)) if (!state.trash.some((job) => job.id === id)) state.picks.delete(id);
  if (state.picking && !state.trash.length) state.picking = false;
  if (arrived) { chime(); window.setTimeout(render, 2600); }
  ensureSelection();
}

function onJob(job) {
  if (!job || !job.id) return;
  if (job.status === "canceled") { dropLocal(job.id); render(); return; }
  const bin = Boolean(job.trashed_at);
  const list = bin ? state.trash : state.jobs;
  const other = bin ? state.jobs : state.trash;
  const arrived = !bin && !state.seen.has(job.id);
  state.seen.add(job.id);
  const stripped = other.filter((item) => item.id !== job.id);
  if (bin) state.jobs = stripped;
  else { state.trash = stripped; state.picks.delete(job.id); }
  const index = list.findIndex((item) => item.id === job.id);
  if (index >= 0) list[index] = job;
  else list.unshift(job);
  list.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  if (!state.trash.length) state.picking = false;
  if (arrived) { state.fresh.set(job.id, Date.now()); chime(); window.setTimeout(render, 2600); }
  if (state.selected === job.id && job.status !== "ready") state.note = "";
  ensureSelection();
  render();
}

function dropLocal(id) {
  state.jobs = state.jobs.filter((job) => job.id !== id);
  state.trash = state.trash.filter((job) => job.id !== id);
  state.picks.delete(id);
  state.seen.delete(id);
  forget(id);
  if (!state.trash.length) state.picking = false;
  ensureSelection();
}

function forget(id) {
  const url = state.previews[id];
  if (url) URL.revokeObjectURL(url);
  delete state.previews[id];
  delete state.drafts[id];
  state.fresh.delete(id);
  if (state.selected === id) { state.selected = null; resetPaper(); }
}

function ensureSelection() {
  if (state.picking) return;
  const jobs = listed();
  if (state.selected && jobs.some((job) => job.id === state.selected)) return;
  const waiting = state.view === "files" ? jobs.find((job) => job.status !== "done") : null;
  state.selected = (waiting || jobs[0] || {}).id || null;
  resetPaper();
}

function select(id) {
  if (state.view === "trash" && state.picking) {
    if (state.picks.has(id)) state.picks.delete(id);
    else state.picks.add(id);
    state.note = "";
    render();
    return;
  }
  if (state.selected === id) return;
  state.selected = id;
  state.note = "";
  resetPaper();
  render();
}

function listed() { return state.view === "trash" ? state.trash : state.jobs; }

function current() { return listed().find((job) => job.id === state.selected) || null; }

function draftOf(job) {
  const count = job.page_count || 1;
  const existing = state.drafts[job.id];
  // Keep the same object across paints. Replacing it while the buttons still close over the old one drops the click.
  if (!existing) return storeDraft(job, count);
  if (existing.dirty) return holdDraft(existing, count);
  if (sameDraft(existing, job, count)) return existing;
  return storeDraft(job, count);
}

function storeDraft(job, count) {
  const draft = freshDraft(job, count);
  state.drafts[job.id] = draft;
  return draft;
}

function sameDraft(draft, job, count) {
  const read = readPages(job.pages, count);
  return draft.choice === read.choice && draft.from === read.from && draft.to === read.to && draft.copies === (job.copies || 1) && draft.count === count;
}

function freshDraft(job, count) {
  const read = readPages(job.pages, count);
  const draft = { choice: read.choice, from: read.from, to: read.to, count, copies: job.copies || 1, dirty: false, focus: "" };
  draft.pages = writePages(draft);
  return draft;
}

function holdDraft(draft, count) {
  draft.count = count;
  draft.from = clampPage(draft.from, count);
  draft.to = clampPage(draft.to, count);
  draft.pages = writePages(draft);
  return draft;
}

function render() {
  renderQueue();
  renderIntro();
  renderPaper();
  renderControls();
  renderPrinter();
  renderToast();
  renderBin();
  renderAsk();
}

function renderQueue() {
  const trash = state.view === "trash";
  const root = document.getElementById("queue");
  if (root) root.setAttribute("aria-label", trash ? "Trash" : "Files");
  paintQueue(root, {
    jobs: trash ? state.trash : state.jobs,
    selected: state.selected,
    folds: trash ? state.trashFolds : state.folds,
    fresh: trash ? () => false : isFresh,
    onSelect: select,
    onToggle: (id, open) => toggleFold(id, open, trash),
    picking: trash && state.picking,
    picks: state.picks,
    waiting: !trash,
  });
}

function toggleFold(id, open, trash) {
  const folds = trash ? state.trashFolds : state.folds;
  const next = !open;
  if (next) { folds.forced.add(id); folds.shut.delete(id); }
  else { folds.shut.add(id); folds.forced.delete(id); }
  if (!setOpen(document.getElementById("queue"), id, next)) renderQueue();
}

function isFresh(id) {
  const at = state.fresh.get(id);
  return Boolean(at && Date.now() - at < 2500);
}

function renderIntro() {
  const intro = document.getElementById("intro");
  if (state.view === "trash" && state.picking) {
    const count = state.picks.size;
    const key = "picking\n" + count;
    if (intro.dataset.key === key) return;
    intro.dataset.key = key;
    const title = count === 0 ? "Select files" : count === 1 ? "1 file selected" : count + " files selected";
    const body = count === 0 ? "Choose the files you want to delete." : "Delete will ask before they’re gone for good.";
    intro.replaceChildren(el("h1", { class: "ticket", text: title }), el("p", { class: "quiet", text: body }));
    return;
  }
  const job = current();
  if (!job) {
    const key = (state.view === "trash" ? "trash:" : "files:") + (state.offline ? "offline" : "empty");
    if (intro.dataset.key === key) return;
    intro.dataset.key = key;
    const block = el("div", { class: "empty" });
    if (state.view === "trash") block.append(el("h1", { text: "Trash is empty." }), el("p", { class: "quiet", text: state.offline ? "The counter lost its connection. It will try again." : "Files you delete stay here until you delete them for good." }));
    else block.append(el("h1", { text: "Nothing is waiting." }), el("p", { class: "quiet", text: state.offline ? "The counter lost its connection. It will try again." : "When someone sends a file, it will show up here." }));
    intro.replaceChildren(block);
    return;
  }
  const showMessage = Boolean(job.message) && job.status !== "ready";
  const key = [state.view, job.id, job.name, showMessage ? job.message : "", job.status].join("\n");
  if (intro.dataset.key === key) return;
  intro.dataset.key = key;
  const nodes = [el("h1", { class: "ticket", text: job.name || "Untitled", attrs: { title: job.name || "" } })];
  if (state.view === "trash") nodes.push(el("p", { class: "quiet", text: "In Trash." }));
  if (showMessage) nodes.push(el("p", { class: "message", text: job.message, attrs: { "data-status": job.status || "" } }));
  intro.replaceChildren(...nodes);
}

function renderPaper() {
  const slot = document.getElementById("paper");
  if (state.view === "trash" && state.picking) {
    if (slot.dataset.key !== "off") { slot.dataset.key = "off"; slot.hidden = true; slot.replaceChildren(); }
    return;
  }
  const job = current();
  const key = job && job.page_count ? job.id : "";
  if (slot.dataset.key === key) return;
  slot.dataset.key = key;
  if (!key) { slot.hidden = true; slot.replaceChildren(); return; }
  slot.hidden = false;
  slot.replaceChildren(el("p", { class: "quiet", text: "Opening the pages…" }));
  showPreview(job);
}

function resetPaper() {
  const slot = document.getElementById("paper");
  // Drop the marker. An empty one already means this file has no pages, so it cannot also mean the page should be drawn again.
  if (slot) delete slot.dataset.key;
}

async function showPreview(job) {
  const cached = state.previews[job.id];
  if (cached) { mountFrame(job.id, cached); return; }
  try {
    const response = await fetch("/admin/jobs/" + job.id + "/file");
    if (!response.ok || state.selected !== job.id) return;
    const url = URL.createObjectURL(await response.blob());
    for (const [id, old] of Object.entries(state.previews)) { URL.revokeObjectURL(old); delete state.previews[id]; }
    if (state.selected !== job.id) { URL.revokeObjectURL(url); return; }
    state.previews[job.id] = url;
    mountFrame(job.id, url);
  } catch {
    const slot = document.getElementById("paper");
    if (slot && state.selected === job.id) slot.replaceChildren(el("p", { class: "quiet", text: "The pages aren't ready to look at yet." }));
  }
}

function mountFrame(id, url) {
  const slot = document.getElementById("paper");
  if (!slot || slot.dataset.key !== id) return;
  const page = el("div", { class: "sheet-page" });
  const frame = document.createElement("iframe");
  frame.title = "Pages";
  // Hide the viewer's own bar so the page looks like paper, not a second app.
  frame.src = url + "#toolbar=0&navpanes=0&view=Fit&zoom=page-fit";
  page.append(frame);
  const nodes = [page];
  if (state.view !== "trash") nodes.push(el("p", { class: "caption", text: "The printer is black and white. This is how the page will look." }));
  slot.replaceChildren(...nodes);
}

function renderControls() {
  const node = document.getElementById("controls");
  if (state.view === "trash") { renderTrashControls(node); return; }
  const job = current();
  if (!job) {
    if (node.dataset.key !== "") { node.dataset.key = ""; node.replaceChildren(); }
    return;
  }
  const draft = draftOf(job);
  const key = [job.id, job.status, job.can_print, job.can_retry, job.page_count, draft.choice, draft.from, draft.to, draft.copies, state.working, state.note].join("|");
  if (node.dataset.key === key) return;
  const wasOpen = Boolean(node.querySelector(".page-span.open"));
  const focus = draft.focus || "";
  const typing = boundFocus();
  draft.focus = "";
  node.dataset.key = key;
  node.replaceChildren();
  if (job.can_print) node.append(settings(job, draft, wasOpen));
  if (job.status === "printing" || state.working === "print") node.append(el("button", { class: "go", text: "Printing…", disabled: true }));
  else if (job.can_print || job.can_retry) node.append(action(job));
  if (state.note) node.append(el("p", { class: "note", text: state.note }));
  node.append(deleteRow(job));
  restoreFocus(focus, typing, wasOpen);
}

function settings(job, draft, wasOpen) {
  const row = el("div", { class: "settings" });
  if (job.page_count > 1) row.append(paintPages(draft, job, { wasOpen, onChange: () => render() }));
  else if (job.page_count === 1) row.append(el("p", { class: "hint alone", text: "1 page" }));
  row.append(copiesField(job, draft));
  return row;
}

function boundFocus() {
  const field = document.activeElement;
  if (!field || (field.id !== "page-from" && field.id !== "page-to")) return null;
  return { id: field.id, caret: field.selectionStart };
}

function restoreFocus(focus, typing, wasOpen) {
  if (focus) {
    const select = focus === "page-from" || focus === "page-to";
    if (select && !wasOpen) requestAnimationFrame(() => focusField(focus, null, true));
    else focusField(focus, null, select);
    return;
  }
  if (typing) focusField(typing.id, typing.caret, false);
}

function focusField(id, caret, select) {
  const field = document.getElementById(id);
  if (!field) return;
  field.focus();
  if (caret != null && field.setSelectionRange) field.setSelectionRange(caret, caret);
  else if (select && field.select) field.select();
}

function copiesField(job, draft) {
  const wrap = el("div", { class: "field" });
  wrap.append(el("span", { text: "Copies" }));
  const stepper = el("div", { class: "stepper" });
  stepper.append(
    step("−", "Fewer copies", draft.copies <= 1, () => bump(job, -1)),
    el("strong", { text: String(draft.copies) }),
    step("+", "More copies", draft.copies >= COPY_LIMIT, () => bump(job, 1)),
  );
  wrap.append(stepper);
  return wrap;
}

function step(text, label, disabled, onClick) {
  return el("button", { class: "step", text: text, disabled: disabled, attrs: { "aria-label": label }, on: { click: onClick } });
}

function bump(job, delta) {
  const draft = draftOf(job);
  const next = Math.min(COPY_LIMIT, Math.max(1, draft.copies + delta));
  if (next === draft.copies) return;
  draft.copies = next;
  draft.dirty = true;
  render();
}

function action(job) {
  if (job.can_retry && !job.can_print) {
    return el("button", { class: "go", text: state.working ? "One moment…" : "Try again", disabled: Boolean(state.working), on: { click: retryCurrent } });
  }
  const again = job.status === "done" || job.status === "failed";
  const label = state.working === "print" ? "Printing…" : again ? "Print again" : "Print";
  return el("button", { class: "go", text: label, disabled: Boolean(state.working), on: { click: printCurrent } });
}

function renderTrashControls(node) {
  if (state.picking) {
    if (node.dataset.key !== "picking") { node.dataset.key = "picking"; node.replaceChildren(); }
    return;
  }
  const job = current();
  if (!job) { if (node.dataset.key !== "") { node.dataset.key = ""; node.replaceChildren(); } return; }
  const key = ["trash", job.id, state.working, state.note].join("|");
  if (node.dataset.key === key) return;
  node.dataset.key = key;
  node.replaceChildren();
  node.append(el("button", { class: "restore", text: state.working ? "One moment…" : "Restore", disabled: Boolean(state.working), on: { click: () => restore(job.id) } }));
  if (state.note) node.append(el("p", { class: "note", text: state.note }));
}

function deleteRow(job) {
  const button = el("button", {
    class: "texty remove",
    disabled: Boolean(state.working),
    attrs: { "aria-label": "Delete " + (job.name || "this file") },
    on: { click: () => moveToTrash(job.id) },
  });
  button.append(trashIcon(), el("span", { text: "Delete" }));
  return button;
}

async function printCurrent() {
  const job = current();
  if (!job || state.working || !job.can_print) return;
  const draft = draftOf(job);
  const pages = job.page_count > 1 ? writePages(draft) : "all";
  state.working = "print";
  state.note = "";
  render();
  try {
    const body = await sendJSON("POST", "/admin/jobs/" + job.id + "/print", { pages, copies: draft.copies });
    if (!body.ok) state.note = body.message || "Please try that again in a moment.";
    else { draft.dirty = false; onJob(body.job); loadPrinter(); return; }
  } catch {
    state.note = "Please try that again in a moment.";
  } finally {
    state.working = "";
    render();
  }
}

async function retryCurrent() {
  const job = current();
  if (!job || state.working || !job.can_retry) return;
  state.working = "retry";
  state.note = "";
  render();
  try {
    const body = await sendJSON("POST", "/admin/jobs/" + job.id + "/retry");
    if (!body.ok) state.note = body.message || "Please try that again in a moment.";
    else { onJob(body.job); return; }
  } catch {
    state.note = "Please try that again in a moment.";
  } finally {
    state.working = "";
    render();
  }
}

async function moveToTrash(id) {
  if (state.working) return;
  state.working = "trash";
  state.note = "";
  render();
  try {
    const body = await sendJSON("POST", "/admin/jobs/" + id + "/trash");
    if (!body.ok) { state.note = body.message || "Please try that again in a moment."; return; }
    showToast(body.message || "Moved to Trash.", id);
    if (body.job) onJob(body.job);
  } catch {
    state.note = "Please try that again in a moment.";
  } finally {
    state.working = "";
    render();
  }
}

async function restore(id) {
  if (!id || state.working) return;
  state.working = "restore";
  state.toast = "";
  state.undo = "";
  state.note = "";
  render();
  try {
    const body = await sendJSON("POST", "/admin/jobs/" + id + "/restore");
    if (!body.ok) { state.note = body.message || "Please try that again in a moment."; return; }
    showToast(body.message || "Back at the counter.");
    if (body.job) onJob(body.job);
  } catch {
    state.note = "Please try that again in a moment.";
  } finally {
    state.working = "";
    render();
  }
}

async function forgetPicked() {
  if (state.working) return;
  const ids = state.trash.filter((job) => state.picks.has(job.id)).map((job) => job.id);
  if (!ids.length) { state.ask = false; render(); return; }
  state.working = "delete";
  render();
  let message = "Deleted.";
  let failed = "";
  try {
    for (const id of ids) {
      const body = await sendJSON("DELETE", "/admin/jobs/" + id);
      if (!body.ok) { failed = body.message || "Please try that again in a moment."; break; }
      if (body.message) message = body.message;
      dropLocal(id);
    }
  } catch {
    failed = "Please try that again in a moment.";
  } finally {
    state.working = "";
    state.ask = false;
    if (failed) state.note = failed;
    else { state.picking = false; state.picks.clear(); state.note = ""; showToast(message); }
    ensureSelection();
    render();
  }
}

function showToast(message, undoId) {
  state.toast = message;
  state.undo = undoId || "";
  window.setTimeout(() => { if (state.toast === message) { state.toast = ""; state.undo = ""; render(); } }, 7000);
}

function renderToast() {
  let toast = document.getElementById("toast");
  if (!state.toast) { if (toast) toast.remove(); return; }
  if (!toast) {
    toast = el("div", { class: "toast", attrs: { id: "toast", role: "status" } });
    document.body.append(toast);
  }
  const key = state.toast + "\n" + state.undo;
  if (toast.dataset.key === key) return;
  toast.dataset.key = key;
  toast.replaceChildren(el("span", { text: state.toast }));
  if (state.undo) toast.append(el("button", { class: "toast-undo", text: "Undo", on: { click: () => restore(state.undo) } }));
}

function renderBin() {
  paintBin({
    view: state.view,
    count: state.trash.length,
    picking: state.picking,
    pickCount: state.picks.size,
    allOn: state.trash.length > 0 && state.picks.size === state.trash.length,
    working: state.working,
    note: state.view === "trash" && state.picking ? state.note : "",
    onOpen: openTrash,
    onClose: closeTrash,
    onPick: startPicking,
    onCancel: stopPicking,
    onAll: toggleAll,
    onDelete: requestDelete,
  });
}

function renderAsk() {
  const chosen = state.trash.filter((job) => state.picks.has(job.id));
  const body = chosen.length === 1 ? (chosen[0].name || "This file") + " will be gone for good." : "These " + chosen.length + " files will be gone for good.";
  paintAsk({ open: state.ask && chosen.length > 0, busy: state.working === "delete", body: body, onYes: forgetPicked, onNo: closeAsk });
}

function openTrash() {
  if (state.view === "trash" || state.working) return;
  state.view = "trash";
  state.picking = false;
  state.picks.clear();
  state.ask = false;
  state.note = "";
  state.selected = null;
  const root = document.getElementById("queue");
  if (root) root.scrollTop = 0;
  ensureSelection();
  render();
}

function closeTrash() {
  if (state.working === "delete") return;
  state.view = "files";
  state.picking = false;
  state.picks.clear();
  state.ask = false;
  state.note = "";
  state.selected = null;
  const root = document.getElementById("queue");
  if (root) root.scrollTop = 0;
  ensureSelection();
  render();
}

function startPicking() {
  if (!state.trash.length || state.working) return;
  state.picking = true;
  state.ask = false;
  state.note = "";
  render();
}

function stopPicking() {
  if (state.working === "delete") return;
  state.picking = false;
  state.picks.clear();
  state.ask = false;
  state.note = "";
  ensureSelection();
  render();
}

function toggleAll() {
  if (state.picks.size === state.trash.length) state.picks.clear();
  else for (const job of state.trash) state.picks.add(job.id);
  state.note = "";
  render();
}

function requestDelete() {
  if (!state.picks.size || state.working) return;
  state.ask = true;
  state.note = "";
  render();
}

function closeAsk() {
  if (state.working === "delete") return;
  state.ask = false;
  render();
}

function onKey(event) {
  if (event.key !== "Escape") return;
  if (state.ask) { event.preventDefault(); closeAsk(); return; }
  if (state.picking) { event.preventDefault(); stopPicking(); }
}

function renderPrinter() {
  const node = document.getElementById("printer");
  if (!node) return;
  let message = "Checking the printer…";
  let status = "";
  if (state.offline) { message = "Trying again…"; status = "down"; }
  else if (state.printer) { message = state.printer.message || message; status = state.printer.state || ""; }
  else if (state.printerLost) { message = "The printer status isn't available right now."; status = "down"; }
  node.dataset.state = status;
  const text = node.querySelector("span");
  if (text.textContent !== message) text.textContent = message;
}

async function readJSON(url) {
  const response = await fetch(url);
  return response.json();
}

async function sendJSON(method, url, payload) {
  const options = { method: method };
  if (payload != null) { options.headers = { "Content-Type": "application/json" }; options.body = JSON.stringify(payload); }
  const response = await fetch(url, options);
  return response.json();
}

let audioCtx = null;

function warmSound() {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return;
  if (!audioCtx) audioCtx = new Ctx();
  if (audioCtx.state === "suspended") audioCtx.resume();
}

function chime() {
  warmSound();
  if (!audioCtx) return;
  const play = () => { const now = audioCtx.currentTime; tone(523.25, now, 0.09); tone(659.25, now + 0.08, 0.16); };
  if (audioCtx.state === "suspended") audioCtx.resume().then(play).catch(() => {});
  else play();
}

function tone(freq, when, duration) {
  const osc = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  osc.type = "sine";
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(0.0001, when);
  gain.gain.exponentialRampToValueAtTime(0.045, when + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, when + duration);
  osc.connect(gain).connect(audioCtx.destination);
  osc.start(when);
  osc.stop(when + duration + 0.02);
}

boot();
