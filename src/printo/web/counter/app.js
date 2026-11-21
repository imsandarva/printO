/* The counter. The live stream is only a nudge; the job list is what we show.
   The preview is grey because this printer is black and white. */

const COPY_LIMIT = 20;
const state = {
  jobs: [],
  seen: new Set(),
  fresh: new Map(),
  drafts: {},
  previews: {},
  selected: null,
  printer: null,
  printerLost: false,
  offline: false,
  live: false,
  working: "",
  confirm: null,
  note: "",
  toast: "",
};

function boot() {
  document.addEventListener("pointerdown", warmSound, { passive: true });
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
    const body = await readJSON("/admin/jobs");
    if (!body.ok || !Array.isArray(body.jobs)) throw new Error("jobs");
    absorb(body.jobs, announce);
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

function absorb(jobs, announce) {
  const ids = new Set();
  let arrived = false;
  for (const job of jobs) {
    ids.add(job.id);
    if (!state.seen.has(job.id)) {
      state.seen.add(job.id);
      if (announce) { arrived = true; state.fresh.set(job.id, Date.now()); }
    }
  }
  for (const id of Array.from(state.seen)) if (!ids.has(id)) { state.seen.delete(id); forget(id); }
  state.jobs = jobs.slice();
  if (arrived) { chime(); window.setTimeout(render, 2600); }
  ensureSelection();
}

function onJob(job) {
  if (!job || !job.id) return;
  if (job.status === "canceled") {
    state.jobs = state.jobs.filter((item) => item.id !== job.id);
    state.seen.delete(job.id);
    forget(job.id);
    ensureSelection();
    render();
    return;
  }
  const arrived = !state.seen.has(job.id);
  state.seen.add(job.id);
  const index = state.jobs.findIndex((item) => item.id === job.id);
  if (index >= 0) state.jobs[index] = job;
  else state.jobs.unshift(job);
  state.jobs.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  if (arrived) { state.fresh.set(job.id, Date.now()); chime(); window.setTimeout(render, 2600); }
  if (state.selected === job.id && job.status !== "ready") state.note = "";
  ensureSelection();
  render();
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
  if (state.selected && state.jobs.some((job) => job.id === state.selected)) return;
  const waiting = state.jobs.find((job) => job.status !== "done");
  state.selected = (waiting || state.jobs[0] || {}).id || null;
  resetPaper();
}

function select(id) {
  if (state.selected === id) return;
  state.selected = id;
  state.confirm = null;
  state.note = "";
  resetPaper();
  render();
}

function current() { return state.jobs.find((job) => job.id === state.selected) || null; }

function draftOf(job) {
  const existing = state.drafts[job.id];
  if (existing && existing.dirty) return existing;
  const draft = { pages: job.pages || "all", copies: job.copies || 1, dirty: false };
  state.drafts[job.id] = draft;
  return draft;
}

function render() {
  renderQueue();
  renderIntro();
  renderPaper();
  renderControls();
  renderPrinter();
  renderToast();
}

function renderQueue() {
  const queue = document.getElementById("queue");
  if (!queue) return;
  const top = queue.scrollTop;
  const waiting = state.jobs.filter((job) => job.status !== "done");
  const earlier = state.jobs.filter((job) => job.status === "done");
  queue.replaceChildren();
  const waitingNode = group("Waiting", waiting);
  const earlierNode = group("Earlier", earlier);
  if (waitingNode) queue.append(waitingNode);
  if (earlierNode) queue.append(earlierNode);
  queue.scrollTop = top;
}

function group(title, jobs) {
  if (!jobs.length) return null;
  const section = el("section", { class: "group" });
  section.append(el("h2", { text: title }));
  for (const job of jobs) section.append(card(job));
  return section;
}

function card(job) {
  const classes = ["card", job.id === state.selected ? "on" : "", isFresh(job.id) ? "fresh" : ""].filter(Boolean).join(" ");
  const button = el("button", { class: classes, attrs: { "aria-pressed": job.id === state.selected ? "true" : "false" }, on: { click: () => select(job.id) } });
  const top = el("div", { class: "card-top" });
  top.append(el("span", { class: "num", text: job.number }), el("span", { class: "when", text: ago(job.created_at) }));
  const label = el("span", { class: "label", text: job.label || "", attrs: { "data-status": job.status || "" } });
  button.append(top, el("span", { class: "file", text: job.name || "" }), label);
  return button;
}

function isFresh(id) {
  const at = state.fresh.get(id);
  return Boolean(at && Date.now() - at < 2500);
}

function renderIntro() {
  const intro = document.getElementById("intro");
  const job = current();
  if (!job) {
    const key = state.offline ? "offline" : "empty";
    if (intro.dataset.key === key) return;
    intro.dataset.key = key;
    const block = el("div", { class: "empty" });
    block.append(el("h1", { text: "Nothing is waiting." }), el("p", { class: "quiet", text: state.offline ? "The counter lost its connection. It will try again." : "When someone sends a file, it will show up here." }));
    intro.replaceChildren(block);
    return;
  }
  const key = [job.id, job.name, job.message, job.status].join("\n");
  if (intro.dataset.key === key) return;
  intro.dataset.key = key;
  const message = el("p", { class: "message", text: job.message || "", attrs: { "data-status": job.status || "" } });
  intro.replaceChildren(el("h1", { class: "ticket", text: job.number }), el("p", { class: "name", text: job.name || "", attrs: { title: job.name || "" } }), message);
}

function renderPaper() {
  const slot = document.getElementById("paper");
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
  if (slot) slot.dataset.key = "";
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
  slot.replaceChildren(page, el("p", { class: "caption", text: "The printer is black and white. This is how the page will look." }));
}

function renderControls() {
  const node = document.getElementById("controls");
  const job = current();
  if (!job) {
    if (node.dataset.key !== "") { node.dataset.key = ""; node.replaceChildren(); }
    return;
  }
  const draft = draftOf(job);
  const key = [job.id, job.status, job.can_print, job.can_retry, job.page_count, draft.copies, state.confirm === job.id, state.working, state.note].join("|");
  if (node.dataset.key === key) return;
  const typing = document.activeElement && document.activeElement.id === "pages";
  const caret = typing ? document.activeElement.selectionStart : null;
  node.dataset.key = key;
  node.replaceChildren();
  if (job.can_print) node.append(settings(job, draft));
  if (job.status === "printing" || state.working === "print") node.append(el("button", { class: "go", text: "Printing…", disabled: true }));
  else if (job.can_print || job.can_retry) node.append(action(job));
  if (state.note) node.append(el("p", { class: "note", text: state.note }));
  node.append(removeRow(job));
  if (typing) restorePages(caret);
}

function settings(job, draft) {
  const row = el("div", { class: "settings" });
  if (job.page_count > 1) row.append(pagesField(draft, job));
  else if (job.page_count === 1) row.append(el("p", { class: "hint alone", text: "1 page" }));
  row.append(copiesField(job, draft));
  return row;
}

function pagesField(draft, job) {
  const wrap = el("label", { class: "field" });
  wrap.append(el("span", { text: "Pages" }));
  const input = document.createElement("input");
  input.id = "pages";
  input.type = "text";
  input.value = draft.pages;
  input.maxLength = 80;
  input.spellcheck = false;
  input.autocomplete = "off";
  input.setAttribute("aria-describedby", "pages-hint");
  input.addEventListener("input", () => { draft.pages = input.value; draft.dirty = true; });
  const hint = el("span", { class: "hint", text: job.page_count + " pages. All of them, or a range like 1-3, 5." });
  hint.id = "pages-hint";
  wrap.append(input, hint);
  return wrap;
}

function restorePages(caret) {
  const field = document.getElementById("pages");
  if (!field) return;
  field.focus();
  if (caret != null) field.setSelectionRange(caret, caret);
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

function removeRow(job) {
  if (state.confirm === job.id) {
    const row = el("div", { class: "confirm" });
    row.append(el("button", { class: "danger", text: "Yes, remove it", disabled: Boolean(state.working), on: { click: () => reallyRemove(job.id) } }), el("button", { class: "texty", text: "Keep it", on: { click: () => { state.confirm = null; render(); } } }));
    return row;
  }
  return el("button", { class: "texty remove", text: "Remove", on: { click: () => { state.confirm = job.id; state.note = ""; render(); } } });
}

async function printCurrent() {
  const job = current();
  if (!job || state.working || !job.can_print) return;
  const draft = draftOf(job);
  state.working = "print";
  state.note = "";
  render();
  try {
    const body = await sendJSON("POST", "/admin/jobs/" + job.id + "/print", { pages: cleanPages(draft.pages), copies: draft.copies });
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

async function reallyRemove(id) {
  if (state.working) return;
  state.working = "remove";
  render();
  try {
    const body = await sendJSON("DELETE", "/admin/jobs/" + id);
    if (!body.ok) { state.note = body.message || "Please try that again in a moment."; return; }
    if (body.message && body.message !== "Removed.") showToast(body.message);
    state.jobs = state.jobs.filter((job) => job.id !== id);
    state.seen.delete(id);
    forget(id);
    ensureSelection();
  } catch {
    state.note = "Please try that again in a moment.";
  } finally {
    state.working = "";
    state.confirm = null;
    render();
  }
}

function cleanPages(value) {
  const text = String(value || "").trim();
  return text || "all";
}

function showToast(message) {
  state.toast = message;
  window.setTimeout(() => { if (state.toast === message) { state.toast = ""; render(); } }, 7000);
}

function renderToast() {
  let toast = document.getElementById("toast");
  if (!state.toast) { if (toast) toast.remove(); return; }
  if (!toast) {
    toast = el("p", { class: "toast", attrs: { id: "toast", role: "status" } });
    document.body.append(toast);
  }
  toast.textContent = state.toast;
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

function ago(iso) {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, (Date.now() - then) / 1000);
  if (seconds < 45) return "Just now";
  if (seconds < 3600) return Math.round(seconds / 60) + " min ago";
  if (seconds < 86400) return Math.round(seconds / 3600) + " hr ago";
  return "Earlier";
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

function el(tag, props) {
  const node = document.createElement(tag);
  const options = props || {};
  if (options.class) node.className = options.class;
  if (options.text != null) node.textContent = options.text;
  if (options.attrs) for (const [key, value] of Object.entries(options.attrs)) if (value != null) node.setAttribute(key, value);
  if (options.disabled) node.disabled = true;
  if (options.on) for (const [key, fn] of Object.entries(options.on)) node.addEventListener(key, fn);
  if (tag === "button") node.type = "button";
  return node;
}

boot();
