/* Small bits of text the page assembles. The sentences themselves come from the server. */

const TYPES = {
  pdf: "PDF", jpg: "JPG", jpeg: "JPG", png: "PNG", webp: "WEBP", gif: "GIF", bmp: "BMP",
  tif: "TIFF", tiff: "TIFF", heic: "HEIC", heif: "HEIC", doc: "DOC", docx: "DOCX", odt: "ODT", rtf: "RTF",
};

export function fill(template, values) {
  let text = template || "";
  for (const [key, value] of Object.entries(values || {})) text = text.replaceAll("{" + key + "}", String(value));
  return text;
}

export function filesLabel(copy, count) {
  if (count === 1) return copy.count_one;
  return fill(copy.count_many, { count });
}

export function sizeLabel(bytes) {
  const size = Number(bytes) || 0;
  if (size < 1024) return size + " B";
  if (size < 1024 * 1024) return Math.max(1, Math.round(size / 1024)) + " KB";
  const mb = size / (1024 * 1024);
  const shown = mb >= 10 ? String(Math.round(mb)) : trim(mb.toFixed(1));
  return shown + " MB";
}

export function typeName(ext) {
  if (!ext) return "FILE";
  return TYPES[ext] || String(ext).slice(0, 4).toUpperCase();
}

function trim(text) {
  return text.endsWith(".0") ? text.slice(0, -2) : text;
}
