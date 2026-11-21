/* One preview at a time. A phone should not decode a pile of photos and PDFs at once. */

import { pageImage } from "./documents.js";

const queue = [];
let pumping = false;

export function requestThumb(item, done) {
  if (!item || (item.kind !== "image" && item.kind !== "pdf")) return;
  queue.push({ item, done });
  pump();
}

async function pump() {
  if (pumping) return;
  pumping = true;
  while (queue.length) {
    const job = queue.shift();
    if (job.item.dropped) continue;
    const url = await render(job.item);
    if (job.item.dropped) { if (url) URL.revokeObjectURL(url); continue; }
    job.item.thumbUrl = url || "";
    job.item.thumbFailed = !url;
    job.done(job.item);
  }
  pumping = false;
}

async function render(item) {
  try {
    if (item.kind === "pdf") return await pageImage(item.file);
    return await imageThumb(item.file);
  } catch {
    return null;
  }
}

async function imageThumb(file) {
  const bitmap = await createImageBitmap(file);
  try {
    return await downscale(bitmap, 192);
  } finally {
    bitmap.close?.();
  }
}

function downscale(bitmap, width) {
  const scale = Math.min(1, width / Math.max(1, bitmap.width));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  const context = canvas.getContext("2d", { alpha: false });
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob((blob) => resolve(blob ? URL.createObjectURL(blob) : null), "image/jpeg", 0.84));
}
