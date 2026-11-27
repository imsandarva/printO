/* Paint the one page. Progress updates a row; it does not rebuild the list. */

import { el, icon } from "./dom.js";
import { filesLabel, fill, sizeLabel, typeName } from "./format.js";
import { checkIcon, closeIcon, fileIcon, plusIcon } from "./icons.js";
import { counts, meterOf } from "./session.js";

export function createView(handlers) {
  const nodes = {
    page: document.querySelector(".page"),
    link: document.getElementById("link"),
    linkText: document.getElementById("link-text"),
    banner: document.getElementById("banner"),
    main: document.getElementById("main"),
    empty: document.getElementById("empty"),
    files: document.getElementById("files"),
    listHead: document.getElementById("list-head"),
    selected: document.getElementById("selected-label"),
    tally: document.getElementById("tally"),
    phase: document.getElementById("phase"),
    phaseTitle: document.getElementById("phase-title"),
    phaseHelp: document.getElementById("phase-help"),
    phasePct: document.getElementById("phase-pct"),
    list: document.getElementById("list"),
    add: document.getElementById("add"),
    cameraAdd: document.getElementById("camera-add"),
    clear: document.getElementById("clear"),
    done: document.getElementById("done"),
    doneTitle: document.getElementById("done-title"),
    doneBody: document.getElementById("done-body"),
    doneSummary: document.getElementById("done-summary"),
    doneNext: document.getElementById("done-next"),
    more: document.getElementById("more"),
    dock: document.getElementById("dock"),
    keep: document.getElementById("keep"),
    track: document.getElementById("track"),
    bar: document.getElementById("bar"),
    send: document.getElementById("send"),
    toast: document.getElementById("toast"),
    toastText: document.getElementById("toast-text"),
    undo: document.getElementById("undo"),
    note: document.getElementById("note"),
    live: document.getElementById("live"),
  };
  let noteTimer = 0;
  nodes.list.addEventListener("click", (event) => onListClick(event, handlers));
  nodes.clear.addEventListener("click", handlers.onClear);
  nodes.add.addEventListener("click", handlers.onAdd);
  nodes.cameraAdd.addEventListener("click", handlers.onCamera);
  nodes.choose = document.getElementById("choose");
  nodes.choose.addEventListener("click", handlers.onChoose);
  nodes.camera = document.getElementById("camera");
  nodes.camera.addEventListener("click", handlers.onCamera);
  nodes.send.addEventListener("click", handlers.onSend);
  nodes.more.addEventListener("click", handlers.onMore);
  nodes.undo.addEventListener("click", handlers.onUndo);

  return {
    prepare(copy) { prepare(nodes, copy); },
    paint(session) { renderChrome(nodes, session); syncList(nodes, session); },
    patch(item, session) { const row = rowOf(nodes.list, item.id); if (row) fillRow(row, item, session); renderChrome(nodes, session); },
    announce(text) { nodes.live.textContent = ""; nodes.live.textContent = text; },
    flashNote(text) { flash(nodes, text, () => noteTimer, (value) => { noteTimer = value; }); },
    showToast(text) { nodes.toast.hidden = false; nodes.toastText.textContent = text; },
    hideToast() { nodes.toast.hidden = true; },
    confirm(copy, onYes) { confirm(copy, onYes); },
  };
}

function prepare(nodes, copy) {
  nodes.selected.textContent = copy.selected;
  nodes.clear.textContent = copy.remove_all;
  nodes.undo.textContent = copy.undo;
  nodes.more.textContent = copy.send_more;
  nodes.send.textContent = copy.send;
  nodes.add.replaceChildren(plusIcon(), el("span", { text: copy.add }));
  nodes.cameraAdd.replaceChildren(cameraIcon(), el("span", { text: copy.camera_add }));
}

function renderChrome(nodes, session) {
  const copy = session.copy;
  const tally = counts(session);
  nodes.linkText.textContent = session.online ? (session.shopName ? fill(copy.connected_named, { name: session.shopName }) : copy.connected_shop) : copy.offline_short;
  nodes.link.classList.toggle("offline", !session.online);
  nodes.banner.hidden = session.online;
  if (!session.online) nodes.banner.textContent = copy.offline;
  const phase = session.phase;
  nodes.empty.hidden = phase !== "empty";
  nodes.files.hidden = phase === "empty" || phase === "done";
  nodes.done.hidden = phase !== "done";
  nodes.dock.hidden = phase === "empty" || phase === "done";
  nodes.page.classList.toggle("docked", !nodes.dock.hidden);
  nodes.listHead.hidden = phase !== "review";
  nodes.phase.hidden = phase === "review" || phase === "empty" || phase === "done";
  nodes.add.hidden = session.sending;
  nodes.cameraAdd.hidden = session.sending;
  nodes.clear.hidden = session.sending || !session.items.length || session.items.some((item) => item.status === "received");
  if (phase === "sending") paintSending(nodes, session, tally);
  else if (phase === "partial") paintPartial(nodes, copy, tally);
  else if (phase === "failed") paintFailed(nodes, session);
  else { nodes.keep.hidden = true; nodes.track.hidden = true; }
  if (phase === "review") nodes.tally.textContent = tally.count ? fill(copy.tally, { files: filesLabel(copy, tally.count), size: sizeLabel(tally.size) }) : "";
  if (phase === "done") paintDone(nodes, copy, tally);
  else if (nodes.page.dataset.arrived) { nodes.page.dataset.arrived = ""; nodes.done.classList.remove("arrive"); }
  const hasIdle = session.items.some((item) => item.ok && item.status === "idle");
  const hasFailed = session.items.some((item) => item.ok && item.status === "failed");
  nodes.send.disabled = session.sending || !session.online || (!hasIdle && !hasFailed);
  nodes.send.textContent = session.sending ? copy.sending : (!hasIdle && hasFailed ? copy.retry : copy.send);
  nodes.main.setAttribute("aria-busy", session.sending ? "true" : "false");
}

function cameraIcon() {
  return icon('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.5 8.5h2.7l1.25-2h7.1l1.25 2h2.7A1.5 1.5 0 0 1 21 10v7.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5V10a1.5 1.5 0 0 1 1.5-1.5ZM12 16.25a3.75 3.75 0 1 0 0-7.5 3.75 3.75 0 0 0 0 7.5Z" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linejoin="round"/></svg>');
}

function paintSending(nodes, session, tally) {
  const copy = session.copy;
  const meter = meterOf(session);
  const show = meter.known && meter.loaded > 0;
  nodes.phaseTitle.textContent = copy.sending;
  nodes.phaseHelp.textContent = fill(copy.partial, { done: tally.received, total: tally.count });
  nodes.phasePct.textContent = show ? Math.round(meter.ratio * 100) + "%" : "";
  nodes.keep.hidden = false;
  nodes.keep.textContent = copy.keep_open;
  nodes.track.hidden = false;
  nodes.track.classList.toggle("busy", !show);
  nodes.track.setAttribute("aria-valuenow", String(show ? Math.round(meter.ratio * 100) : 0));
  nodes.track.setAttribute("aria-label", copy.sending);
  nodes.bar.style.width = show ? Math.round(meter.ratio * 100) + "%" : "";
}

function paintPartial(nodes, copy, tally) {
  nodes.phaseTitle.textContent = fill(copy.partial, { done: tally.received, total: tally.count });
  nodes.phaseHelp.textContent = copy.partial_help;
  nodes.phasePct.textContent = "";
  nodes.keep.hidden = true;
  nodes.track.hidden = true;
}

function paintFailed(nodes, session) {
  nodes.phaseTitle.textContent = session.copy.none_received;
  nodes.phaseHelp.textContent = failureLine(session);
  nodes.phasePct.textContent = "";
  nodes.keep.hidden = true;
  nodes.track.hidden = true;
}

function paintDone(nodes, copy, tally) {
  nodes.doneTitle.textContent = copy.received_title;
  nodes.doneBody.textContent = copy.received_body;
  nodes.doneSummary.textContent = fill(copy.tally, { files: filesLabel(copy, tally.count), size: sizeLabel(tally.size) });
  nodes.doneNext.textContent = copy.collect;
  if (nodes.page.dataset.arrived === "1") return;
  nodes.page.dataset.arrived = "1";
  nodes.done.classList.remove("arrive");
  void nodes.done.offsetWidth;
  nodes.done.classList.add("arrive");
}

function failureLine(session) {
  const messages = [...new Set(session.items.filter((item) => item.ok && item.status === "failed").map((item) => item.error).filter(Boolean))];
  return messages.length === 1 ? messages[0] : session.copy.try_again_send;
}

function syncList(nodes, session) {
  const ids = new Set(session.items.map((item) => item.id));
  for (const child of [...nodes.list.children]) if (!ids.has(child.dataset.id)) dropRow(child);
  session.items.forEach((item, index) => {
    let row = rowOf(nodes.list, item.id);
    if (!row) { row = buildRow(); row.dataset.id = item.id; row.classList.add("enter"); }
    else if (row.dataset.dropping === "1") restoreRow(row);
    const place = liveRows(nodes.list)[index] || null;
    if (row !== place) nodes.list.insertBefore(row, place);
    fillRow(row, item, session);
  });
}

function onListClick(event, handlers) {
  const row = event.target.closest(".row");
  if (!row || row.dataset.dropping === "1") return;
  const id = row.dataset.id;
  if (event.target.closest(".icon-btn")) { handlers.onRemove(id); return; }
  if (event.target.closest(".retry")) { handlers.onRetry(id); return; }
  if (event.target.closest(".thumb, .name-hit")) handlers.onPreview(id);
}

function buildRow() {
  const row = el("div", { class: "row", attrs: { role: "listitem" } });
  const thumb = el("button", { class: "thumb" });
  const img = el("img", { attrs: { alt: "", draggable: "false" } });
  img.hidden = true;
  const glyph = el("span", { class: "glyph" });
  glyph.append(fileIcon(), el("small"));
  thumb.append(img, glyph);
  const sub = el("span", { class: "sub" });
  const tick = el("i", { class: "tick" });
  tick.append(checkIcon());
  tick.hidden = true;
  sub.append(tick, el("span", { class: "sub-text" }));
  const retry = el("button", { class: "retry" });
  retry.hidden = true;
  const bar = el("span", { class: "mini-bar" });
  bar.append(el("i"));
  bar.hidden = true;
  const open = el("button", { class: "name-hit" });
  open.append(el("span", { class: "name" }), sub);
  const body = el("div", { class: "body" });
  body.append(open, retry, bar);
  const remove = el("button", { class: "icon-btn" });
  remove.append(closeIcon());
  row.append(thumb, body, remove);
  return row;
}

function fillRow(row, item, session) {
  const copy = session.copy;
  row.classList.toggle("bad", item.status === "failed" || item.status === "blocked");
  const thumb = row.querySelector(".thumb");
  const img = thumb.querySelector("img");
  const glyph = thumb.querySelector(".glyph");
  thumb.classList.toggle("photo", item.kind === "image" && Boolean(item.thumbUrl));
  thumb.classList.toggle("page", item.kind === "pdf" && Boolean(item.thumbUrl));
  if (item.thumbUrl) {
    if (img.getAttribute("src") !== item.thumbUrl) img.src = item.thumbUrl;
    img.hidden = false;
    glyph.hidden = true;
  } else { img.hidden = true; glyph.hidden = false; glyph.querySelector("small").textContent = typeName(item.ext); }
  thumb.setAttribute("aria-label", fill(copy.view, { name: item.name }));
  const body = row.querySelector(".body");
  body.querySelector(".name-hit").setAttribute("aria-label", fill(copy.view, { name: item.name }));
  const name = body.querySelector(".name");
  name.textContent = item.name;
  name.title = item.name;
  const sub = body.querySelector(".sub");
  sub.classList.toggle("good", item.status === "received");
  sub.classList.toggle("bad", item.status === "failed" || item.status === "blocked");
  sub.querySelector(".tick").hidden = item.status !== "received";
  sub.querySelector(".sub-text").textContent = metaText(item, copy);
  const retry = body.querySelector(".retry");
  retry.hidden = item.status !== "failed" || session.sending;
  retry.textContent = copy.retry;
  const bar = body.querySelector(".mini-bar");
  const moving = item.status === "uploading" && item.computable && item.total;
  bar.hidden = !moving;
  if (moving) bar.querySelector("i").style.width = Math.min(100, Math.round((100 * item.loaded) / item.total)) + "%";
  const remove = row.querySelector(".icon-btn");
  remove.hidden = session.sending || item.status === "received";
  remove.setAttribute("aria-label", fill(copy.remove, { name: item.name }));
}

function metaText(item, copy) {
  if (item.status === "blocked") return item.error;
  if (item.status === "waiting") return copy.waiting;
  if (item.status === "uploading") return item.computable && item.total ? fill(copy.uploading_pct, { pct: Math.min(100, Math.round((100 * item.loaded) / item.total)) }) : copy.uploading;
  if (item.status === "received") return copy.received_word;
  if (item.status === "failed") return item.error ? copy.failed_word + " · " + item.error : copy.failed_word;
  return typeName(item.ext) + " · " + sizeLabel(item.file.size);
}

function dropRow(child) {
  if (child.dataset.dropping === "1") return;
  child.dataset.dropping = "1";
  child.classList.add("leaving");
  child.style.height = child.offsetHeight + "px";
  const finish = () => { if (child.dataset.dropping === "1") child.remove(); };
  child._drop = finish;
  child.addEventListener("transitionend", finish);
  requestAnimationFrame(() => { if (child.dataset.dropping === "1") child.style.height = "0px"; });
  setTimeout(finish, 240);
}

function restoreRow(row) {
  if (row._drop) row.removeEventListener("transitionend", row._drop);
  row.dataset.dropping = "";
  row.classList.remove("leaving");
  row.style.height = "";
}

function liveRows(list) {
  return [...list.children].filter((node) => node.dataset.dropping !== "1");
}

function rowOf(list, id) {
  const safe = window.CSS && CSS.escape ? CSS.escape(id) : id;
  return list.querySelector('[data-id="' + safe + '"]');
}

function flash(nodes, text, read, write) {
  nodes.note.hidden = false;
  nodes.note.textContent = text;
  clearTimeout(read());
  write(setTimeout(() => { nodes.note.hidden = true; }, 2400));
}

function confirm(copy, onYes) {
  const veil = el("div", { class: "veil", attrs: { role: "dialog", "aria-modal": "true", "aria-labelledby": "ask-title" } });
  const card = el("div", { class: "ask" });
  const yes = el("button", { class: "primary", text: copy.remove_all });
  const no = el("button", { class: "quiet ask-cancel", text: copy.cancel });
  card.append(el("h2", { attrs: { id: "ask-title" }, text: copy.confirm_title }), el("p", { text: copy.confirm_body }), yes, no);
  veil.append(card);
  document.body.append(veil);
  document.body.classList.add("locked");
  no.focus();
  const close = () => { veil.remove(); document.body.classList.remove("locked"); document.removeEventListener("keydown", onKey); };
  const onKey = (event) => { if (event.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  no.addEventListener("click", close);
  veil.addEventListener("click", (event) => { if (event.target === veil) close(); });
  yes.addEventListener("click", () => { close(); onYes(); });
}
