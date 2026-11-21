/* PDF pages, drawn on the phone. The shop wifi has no internet, so the viewer lives here.
   Mozilla pdf.js, Apache-2.0, kept beside this file. */

import * as pdfjs from "./pdf.min.mjs";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("./pdf.worker.min.mjs", import.meta.url).href;

export async function loadPdf(file) {
  const data = new Uint8Array(await file.arrayBuffer());
  return pdfjs.getDocument({ data, disableAutoFetch: true, disableStream: true, isEvalSupported: false, useSystemFonts: true }).promise;
}

export async function pageImage(file) {
  let doc = null;
  try {
    doc = await loadPdf(file);
    const page = await doc.getPage(1);
    const base = page.getViewport({ scale: 1 });
    const viewport = page.getViewport({ scale: 168 / base.width });
    const canvas = document.createElement("canvas");
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.max(1, Math.floor(viewport.width * dpr));
    canvas.height = Math.max(1, Math.floor(viewport.height * dpr));
    const context = canvas.getContext("2d", { alpha: false });
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, viewport.width, viewport.height);
    await page.render({ canvasContext: context, viewport }).promise;
    page.cleanup();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.86));
    return blob ? URL.createObjectURL(blob) : null;
  } catch {
    return null;
  } finally {
    if (doc) doc.destroy();
  }
}
