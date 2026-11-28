/* A screen-sized picture of each page, made once.
   Turning a page or laying two on a landscape sheet redraws that picture.
   The original file is not opened again, so a large scan stays in step with the click.
   The fit is the same rule the printer uses: the turned page, centered, cut off at the edge. */

const CAP = 1600;
const REUSE = 0.8;

export function createProxyCache() {
  return { pages: new Map(), pending: new Map(), stamp: 0, tail: Promise.resolve() };
}

export function rasterEdge(frame) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const long = Math.max(frame?.width || 0, frame?.height || 0);
  return Math.min(CAP, Math.max(64, Math.ceil(long * dpr)));
}

/* A picture is sharp enough when it already covers the box it will be drawn into.
   Turning the sheet sideways must not open the file again just because the box got wider. */
export function cellNeed(frame, half) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const long = half ? Math.max((frame?.width || 0) / 2, frame?.height || 0) : Math.max(frame?.width || 0, frame?.height || 0);
  return Math.max(1, long * dpr);
}

export function proxySharp(proxy, pixelLong) {
  if (!proxy || proxy.closed || !proxy.width || !proxy.height) return false;
  return Math.max(proxy.width, proxy.height) >= pixelLong * REUSE;
}

export function peekProxy(cache, pageNum) {
  const hit = cache?.pages.get(pageNum);
  return hit && !hit.closed ? hit : null;
}

export function pageProxy(cache, doc, pageNum, edge, hooks) {
  const hit = fresh(cache, pageNum, edge);
  if (hit) return Promise.resolve(hit);
  const pending = cache.pending.get(pageNum);
  if (pending && pending.edge >= edge * REUSE) return pending.promise;
  if (pending) return pending.promise.then((proxy) => (fresh(cache, pageNum, edge) ? proxy : pageProxy(cache, doc, pageNum, edge, hooks)));
  const stamp = cache.stamp;
  const promise = enqueue(cache, () => raster(doc, pageNum, edge, stamp, cache, hooks)).then((proxy) => {
    if (!proxy || cache.stamp !== stamp) { closeBitmap(proxy); return null; }
    const prev = cache.pages.get(pageNum);
    cache.pages.set(pageNum, proxy);
    if (prev && prev !== proxy) retire(prev);
    return proxy;
  }).finally(() => {
    if (cache.pending.get(pageNum)?.promise === promise) cache.pending.delete(pageNum);
  });
  cache.pending.set(pageNum, { edge, promise });
  return promise;
}

export function holdProxy(proxy) {
  if (proxy && !proxy.closed) proxy.held = (proxy.held || 0) + 1;
}

export function dropProxy(proxy) {
  if (!proxy) return;
  proxy.held = Math.max(0, (proxy.held || 1) - 1);
  if (!proxy.held && proxy.stale) closeBitmap(proxy);
}

export function clearProxies(cache) {
  if (!cache) return;
  cache.stamp += 1;
  for (const proxy of cache.pages.values()) closeBitmap(proxy);
  cache.pages.clear();
  cache.pending.clear();
}

export function evictProxies(cache, keep) {
  if (!cache) return;
  for (const [num, proxy] of cache.pages) {
    if (keep.has(num) || proxy.held) continue;
    closeBitmap(proxy);
    cache.pages.delete(num);
  }
}

export function paintSheet(canvas, frame, proxy, quarterTurn) {
  const turn = quarter(quarterTurn);
  const ctx = prepareSheet(canvas, frame);
  blitPage(ctx, { x: 0, y: 0, width: frame.width, height: frame.height }, proxy, turn);
  canvas.dataset.rot = String(turn);
  delete canvas.dataset.landscape;
}

export function prepareSheet(canvas, frame) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.max(1, Math.floor(frame.width * dpr));
  canvas.height = Math.max(1, Math.floor(frame.height * dpr));
  const ctx = canvas.getContext("2d", { alpha: false });
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, frame.width, frame.height);
  return ctx;
}

export function blitPage(ctx, cell, proxy, quarterTurn) {
  if (!ctx || !proxy || proxy.closed || !proxy.width || !proxy.height || !cell.width || !cell.height) return;
  const box = turnedSize(proxy, quarterTurn);
  const scale = Math.min(cell.width / box.width, cell.height / box.height);
  ctx.save();
  ctx.beginPath();
  ctx.rect(cell.x, cell.y, cell.width, cell.height);
  ctx.clip();
  ctx.translate(cell.x + cell.width / 2, cell.y + cell.height / 2);
  if (box.turn) ctx.rotate((box.turn * Math.PI) / 180);
  ctx.drawImage(proxy.bitmap, (-proxy.width * scale) / 2, (-proxy.height * scale) / 2, proxy.width * scale, proxy.height * scale);
  ctx.restore();
}

export function quarter(value) {
  const turn = ((Math.round(Number(value)) || 0) % 360 + 360) % 360;
  return turn === 90 || turn === 180 || turn === 270 ? turn : 0;
}

export function turnRatio(frame, proxy, fromTurn, toTurn) {
  if (!proxy || proxy.closed) return 1;
  const from = fitFactor(frame, proxy, fromTurn);
  const to = fitFactor(frame, proxy, toTurn);
  return from > 0 ? to / from : 1;
}

function fitFactor(frame, proxy, quarterTurn) {
  const box = turnedSize(proxy, quarterTurn);
  if (!box.width || !box.height) return 1;
  return Math.min(frame.width / box.width, frame.height / box.height);
}

function turnedSize(proxy, quarterTurn) {
  const turn = quarter(quarterTurn);
  const swap = turn === 90 || turn === 270;
  return { turn, width: swap ? proxy.height : proxy.width, height: swap ? proxy.width : proxy.height };
}

function fresh(cache, pageNum, edge) {
  const hit = cache.pages.get(pageNum);
  if (!hit || hit.closed || hit.edge < edge * REUSE) return null;
  return hit;
}

function enqueue(cache, job) {
  const run = cache.tail.then(job, job);
  cache.tail = run.then(() => undefined, () => undefined);
  return run;
}

async function raster(doc, pageNum, edge, stamp, cache, hooks) {
  if (cache.stamp !== stamp || !hooks.alive()) return null;
  const page = await doc.getPage(pageNum);
  let task = null;
  try {
    if (cache.stamp !== stamp || !hooks.alive()) return null;
    const base = quarter(page.rotate || 0);
    const unit = page.getViewport({ scale: 1, rotation: base });
    const long = Math.max(unit.width, unit.height) || 1;
    const viewport = page.getViewport({ scale: edge / long, rotation: base });
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.ceil(viewport.width));
    canvas.height = Math.max(1, Math.ceil(viewport.height));
    const ctx = canvas.getContext("2d", { alpha: false });
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    task = page.render({ canvasContext: ctx, viewport });
    hooks.track(task);
    try { await task.promise; }
    catch { releaseCanvas(canvas); return null; }
    if (cache.stamp !== stamp || !hooks.alive()) { releaseCanvas(canvas); return null; }
    return { bitmap: canvas, width: canvas.width, height: canvas.height, edge, held: 0, closed: false, stale: false };
  } finally {
    try { page.cleanup(); }
    catch { /* The page was already released with the file. */ }
  }
}

function retire(proxy) {
  if (proxy.held) proxy.stale = true;
  else closeBitmap(proxy);
}

function closeBitmap(proxy) {
  if (!proxy || proxy.closed) return;
  proxy.closed = true;
  releaseCanvas(proxy.bitmap);
}

function releaseCanvas(canvas) {
  if (!canvas) return;
  if (typeof canvas.close === "function") canvas.close();
  else { canvas.width = 0; canvas.height = 0; }
}
