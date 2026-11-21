/* Wires the customer page. The pieces beside this file do the work. */

import { watchShop } from "./connect.js";
import { filesLabel, fill } from "./format.js";
import { createView } from "./render.js";
import { addItems, counts, createSession, keyOf, putBack, releaseItem, resetSession, sendable, syncPhase, takeAll, takeOut } from "./session.js";
import { assess } from "./sniff.js";
import { requestThumb } from "./thumbs.js";
import { uploadPool } from "./transfer.js";
import { openViewer } from "./viewer.js";

const boot = JSON.parse(document.getElementById("boot").textContent);
const session = createSession(boot);
const view = createView({
  onChoose: () => openPicker(),
  onAdd: () => openPicker(),
  onClear: () => askClear(),
  onUndo: () => undo(),
  onSend: () => transmit(sendable(session)),
  onMore: () => startOver(),
  onRemove: (id) => removeOne(id),
  onRetry: (id) => retryOne(id),
  onPreview: (id) => preview(id),
});

bootPage();

function bootPage() {
  const picker = document.getElementById("picker");
  picker.addEventListener("change", () => { const files = picker.files; if (files && files.length) take(files); picker.value = ""; });
  watchDrop();
  window.addEventListener("beforeunload", (event) => { if (!session.sending) return; event.preventDefault(); event.returnValue = ""; });
  view.prepare(session.copy);
  syncPhase(session);
  view.paint(session);
  watchShop((online, name) => { session.online = online; if (online && name) session.shopName = name; view.paint(session); });
}

function openPicker() {
  if (session.sending) return;
  document.getElementById("picker").click();
}

let chain = Promise.resolve();

function take(fileList) {
  const files = [...fileList];
  chain = chain.then(() => ingest(files)).catch(() => {});
}

async function ingest(files) {
  if (session.sending || !files.length) return;
  if (session.phase === "done") startOver(false);
  const rows = [];
  for (const file of files) rows.push({ file, key: keyOf(file), ...(await assess(file, session.maxBytes)) });
  const result = addItems(session, rows);
  syncPhase(session);
  if (result.duplicate) view.flashNote(session.copy.duplicate);
  view.paint(session);
  for (const item of result.added) if (item.ok && (item.kind === "image" || item.kind === "pdf")) requestThumb(item, () => view.patch(item, session));
  const kept = result.added.filter((item) => item.ok);
  if (kept.length) view.announce(filesLabel(session.copy, counts(session).count));
  else if (result.added[0]) view.announce(result.added[0].error);
}

function removeOne(id) {
  if (session.sending) return;
  const item = session.items.find((entry) => entry.id === id);
  if (!item || item.status === "received") return;
  const entry = takeOut(session, id);
  if (!entry) return;
  hold([entry], fill(session.copy.removed_one, { name: entry.item.name }));
  syncPhase(session);
  view.paint(session);
}

function askClear() {
  if (session.sending || !session.items.length || session.items.some((item) => item.status === "received")) return;
  view.confirm(session.copy, () => {
    hold(takeAll(session), session.copy.removed_all);
    syncPhase(session);
    view.paint(session);
    view.announce(session.copy.removed_all);
  });
}

function hold(entries, label) {
  commitUndo();
  session.undo = { entries };
  view.showToast(label);
  session.timer = setTimeout(commitUndo, 5000);
}

function undo() {
  if (!session.undo) return;
  clearTimeout(session.timer);
  const entries = session.undo.entries;
  session.undo = null;
  putBack(session, entries);
  view.hideToast();
  syncPhase(session);
  view.paint(session);
}

function commitUndo() {
  clearTimeout(session.timer);
  const entries = session.undo ? session.undo.entries : [];
  session.undo = null;
  for (const entry of entries) releaseItem(entry.item);
  view.hideToast();
}

function startOver(paint = true) {
  commitUndo();
  for (const item of session.items) releaseItem(item);
  resetSession(session);
  syncPhase(session);
  if (paint) view.paint(session);
}

function preview(id) {
  const item = session.items.find((entry) => entry.id === id);
  if (item) openViewer(item, session);
}

function retryOne(id) {
  const item = session.items.find((entry) => entry.id === id);
  if (item && item.status === "failed") transmit([item]);
}

async function transmit(batch) {
  if (session.sending || !session.online || !batch.length) return;
  session.sending = true;
  for (const item of batch) { item.status = "waiting"; item.loaded = 0; item.computable = false; item.error = ""; }
  syncPhase(session);
  view.paint(session);
  view.announce(session.copy.sending);
  const frames = new Map();
  await uploadPool(batch, {
    start(item) { item.status = "uploading"; view.patch(item, session); },
    progress(item, computable, loaded, total) {
      item.computable = computable;
      item.loaded = loaded;
      item.total = total || item.file.size;
      if (frames.has(item.id)) return;
      frames.set(item.id, requestAnimationFrame(() => { frames.delete(item.id); view.patch(item, session); }));
    },
    done(item, result) {
      if (result.ok) { item.status = "received"; item.loaded = item.file.size; }
      else { item.status = "failed"; item.error = result.offline ? session.copy.offline : (result.message || session.copy.try_again); }
      view.patch(item, session);
      const tally = counts(session);
      view.announce(fill(session.copy.partial, { done: tally.received, total: tally.count }));
    },
  });
  session.sending = false;
  syncPhase(session);
  view.paint(session);
  if (session.phase === "done") view.announce(session.copy.received_title + " " + session.copy.received_body);
}

function watchDrop() {
  let depth = 0;
  document.addEventListener("dragenter", (event) => { if (!event.dataTransfer) return; event.preventDefault(); depth += 1; document.body.classList.add("dropping"); });
  document.addEventListener("dragover", (event) => event.preventDefault());
  document.addEventListener("dragleave", () => { depth = Math.max(0, depth - 1); if (!depth) document.body.classList.remove("dropping"); });
  document.addEventListener("drop", (event) => {
    event.preventDefault();
    depth = 0;
    document.body.classList.remove("dropping");
    const files = event.dataTransfer && event.dataTransfer.files;
    if (files && files.length) take(files);
  });
}
