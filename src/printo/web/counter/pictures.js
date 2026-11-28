/* A picture the shop already saved for one page.
   Turning it, or setting it beside the next page, only moves this picture.
   The file itself is never opened here, and a picture that scrolls away is only
   forgotten on screen. The saved one stays, so coming back is immediate. */

const pending = new WeakMap();

export function pictureUrl(id, page, revision) {
  if (!id || !page || !revision) return "";
  return "/admin/jobs/" + id + "/previews/" + page + "?v=" + encodeURIComponent(revision);
}

export function quarter(value) {
  const turn = ((Math.round(Number(value)) || 0) % 360 + 360) % 360;
  return turn === 90 || turn === 180 || turn === 270 ? turn : 0;
}

/* Fit the picture in its half the way the printer centres a page, then turn it. */
export function placePicture(img, turn) {
  const cell = img.parentElement;
  const nw = img.naturalWidth;
  const nh = img.naturalHeight;
  if (!cell || !nw || !nh) return;
  const cw = cell.clientWidth;
  const ch = cell.clientHeight;
  const q = quarter(turn);
  img.dataset.turn = String(q);
  if (!cw || !ch) {
    if (!cell.hidden) requestAnimationFrame(() => { if (img.isConnected && img.dataset.src) placePicture(img, q); });
    return;
  }
  const swap = q === 90 || q === 270;
  const scale = Math.min(cw / (swap ? nh : nw), ch / (swap ? nw : nh));
  img.style.width = Math.max(1, nw * scale).toFixed(2) + "px";
  img.style.height = Math.max(1, nh * scale).toFixed(2) + "px";
  img.style.transform = "translate(-50%, -50%) rotate(" + q + "deg)";
}

/* Keep whatever is already showing until the next picture has arrived. */
export function loadPicture(img, url, onReady) {
  if (!img || !url) return;
  pending.set(img, onReady);
  if (img.dataset.src === url && img.complete && img.naturalWidth) { onReady(); return; }
  if (img.dataset.want === url) return;
  const probe = new Image();
  probe.decoding = "async";
  probe.onload = () => {
    if (!img.isConnected || img.dataset.want !== url) return;
    img.dataset.src = url;
    if (img.getAttribute("src") !== url) img.src = url;
    const finish = () => { if (img.dataset.src === url) pending.get(img)?.(); };
    if (img.complete && img.naturalWidth) finish();
    else img.onload = finish;
  };
  probe.onerror = () => {};
  img.dataset.want = url;
  probe.src = url;
}

/* Drop the decoded pixels. The saved picture stays in the browser's cache. */
export function releasePicture(img) {
  if (!img) return;
  pending.delete(img);
  img.dataset.want = "";
  img.dataset.src = "";
  img.onload = null;
  img.removeAttribute("src");
  img.classList.remove("is-placed");
  img.style.width = "";
  img.style.height = "";
  img.style.transform = "";
}
