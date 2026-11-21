/* The selection the customer is building. Uploads borrow it; they do not own a second copy. */

let sequence = 0;

export function createSession(boot) {
  return {
    copy: boot.copy,
    maxBytes: Number(boot.max_bytes) || 64 * 1024 * 1024,
    shopName: boot.name || "",
    online: true,
    items: [],
    undo: null,
    phase: "empty",
    sending: false,
    timer: 0,
  };
}

export function keyOf(file) {
  // Name alone collides. Size and the file's own time tell two different "notes.pdf" apart.
  return [file.name, file.size, file.lastModified].join("\0");
}

export function addItems(session, rows) {
  const seen = new Set(session.items.map((item) => item.key));
  const added = [];
  let duplicate = false;
  for (const row of rows) {
    if (seen.has(row.key)) { duplicate = true; continue; }
    seen.add(row.key);
    const item = makeItem(session, row);
    session.items.push(item);
    added.push(item);
  }
  return { added, duplicate };
}

export function takeOut(session, id) {
  const index = session.items.findIndex((item) => item.id === id);
  if (index < 0) return null;
  const [item] = session.items.splice(index, 1);
  return { item, index };
}

export function takeAll(session) {
  const entries = session.items.map((item, index) => ({ item, index }));
  session.items = [];
  return entries;
}

export function putBack(session, entries) {
  const ordered = entries.slice().sort((a, b) => a.index - b.index);
  for (const entry of ordered) session.items.splice(Math.min(entry.index, session.items.length), 0, entry.item);
}

export function releaseItem(item) {
  if (!item || item.dropped) return;
  item.dropped = true;
  if (item.thumbUrl) URL.revokeObjectURL(item.thumbUrl);
  if (item.fullUrl) URL.revokeObjectURL(item.fullUrl);
  item.thumbUrl = "";
  item.fullUrl = "";
}

export function resetSession(session) {
  session.items = [];
  session.phase = "empty";
  session.sending = false;
}

export function sendable(session) {
  return session.items.filter((item) => item.ok && item.status !== "received");
}

export function counts(session) {
  const ok = session.items.filter((item) => item.ok);
  return {
    count: ok.length,
    size: ok.reduce((sum, item) => sum + item.file.size, 0),
    received: ok.filter((item) => item.status === "received").length,
  };
}

export function meterOf(session) {
  let total = 0;
  let loaded = 0;
  let known = true;
  for (const item of session.items) {
    if (!item.ok) continue;
    total += item.file.size;
    if (item.status === "received") loaded += item.file.size;
    else if (item.status === "uploading") {
      if (!item.computable) known = false;
      else loaded += Math.min(item.file.size, item.loaded || 0);
    }
  }
  return { total, loaded, ratio: total ? loaded / total : 0, known };
}

export function syncPhase(session) {
  if (session.sending) { session.phase = "sending"; return; }
  if (!session.items.length) { session.phase = "empty"; return; }
  const ok = session.items.filter((item) => item.ok);
  const received = ok.filter((item) => item.status === "received").length;
  const failed = ok.filter((item) => item.status === "failed").length;
  const pending = ok.filter((item) => item.status === "idle" || item.status === "waiting" || item.status === "uploading").length;
  if (ok.length && received === ok.length) { session.phase = "done"; return; }
  if (failed && !pending && received) { session.phase = "partial"; return; }
  if (failed && !pending && !received) { session.phase = "failed"; return; }
  session.phase = "review";
}

function makeItem(session, row) {
  sequence += 1;
  const reason = row.ok ? "" : (session.copy[row.reason] || session.copy.unsupported);
  return {
    id: "f" + sequence,
    key: row.key,
    file: row.file,
    name: row.file.name || "File",
    ok: Boolean(row.ok),
    kind: row.kind || "",
    ext: row.ext || "",
    status: row.ok ? "idle" : "blocked",
    error: reason,
    loaded: 0,
    total: row.file.size,
    computable: false,
    thumbUrl: "",
    fullUrl: "",
    thumbFailed: false,
    dropped: false,
  };
}
