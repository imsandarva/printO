/* Several files leave together. Three at a time is enough to move as a set, and light on a shop laptop. */

const AT_ONCE = 3;

export function uploadPool(items, hooks) {
  const queue = items.slice();
  const workers = Array.from({ length: Math.min(AT_ONCE, queue.length) }, () => run());
  return Promise.all(workers);

  async function run() {
    while (queue.length) {
      const item = queue.shift();
      hooks.start(item);
      const result = await uploadOne(item, (computable, loaded, total) => hooks.progress(item, computable, loaded, total));
      hooks.done(item, result);
    }
  }
}

function uploadOne(item, onProgress) {
  return new Promise((resolve) => {
    const body = new FormData();
    body.append("file", item.file, item.file.name);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/upload");
    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) { onProgress(false, 0, item.file.size); return; }
      onProgress(true, event.loaded, event.total);
    });
    xhr.addEventListener("load", () => resolve(outcome(xhr)));
    xhr.addEventListener("error", () => resolve({ ok: false, offline: true, message: "" }));
    xhr.addEventListener("abort", () => resolve({ ok: false, offline: true, message: "" }));
    xhr.send(body);
  });
}

function outcome(xhr) {
  let body = {};
  try { body = JSON.parse(xhr.responseText || "{}"); } catch { body = {}; }
  if (xhr.status >= 200 && xhr.status < 300 && body.ok) return { ok: true, message: "" };
  return { ok: false, offline: xhr.status === 0, message: body.message || "" };
}
