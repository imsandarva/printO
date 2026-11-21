/* Decide what a file is from its first bytes, the same way the shop does. The name is only a hint. */

const HEIF = new Set(["heic", "heix", "hevc", "hevx", "heim", "heis", "heif", "mif1", "msf1"]);

export async function assess(file, maxBytes) {
  if (!file || file.size === 0) return { ok: false, reason: "empty", kind: "", ext: "" };
  const found = await classify(file);
  if (file.size > maxBytes) return { ok: false, reason: "too_large", kind: found.kind, ext: found.ext };
  if (!found.ok) return { ok: false, reason: "unsupported", kind: "", ext: found.ext || "" };
  return found;
}

async function classify(file) {
  const head = new Uint8Array(await file.slice(0, 64).arrayBuffer());
  const sniffed = sniff(head);
  if (sniffed) return { ok: true, ...sniffed };
  const ext = extension(file.name);
  // A Word file is a zip. The shop checks the inside; here the header is enough to let them try.
  if ((ext === "docx" || ext === "odt") && isZip(head)) return { ok: true, kind: "doc", ext };
  return { ok: false, kind: "", ext };
}

function sniff(head) {
  if (starts(head, [0x25, 0x50, 0x44, 0x46])) return { kind: "pdf", ext: "pdf" };
  if (starts(head, [0xff, 0xd8, 0xff])) return { kind: "image", ext: "jpg" };
  if (starts(head, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) return { kind: "image", ext: "png" };
  if (startsText(head, "GIF87a") || startsText(head, "GIF89a")) return { kind: "image", ext: "gif" };
  if (startsText(head, "BM")) return { kind: "image", ext: "bmp" };
  if (starts(head, [0x49, 0x49, 0x2a, 0x00]) || starts(head, [0x4d, 0x4d, 0x00, 0x2a])) return { kind: "image", ext: "tiff" };
  if (head.length >= 12 && startsText(head, "RIFF") && text(head, 8, 12) === "WEBP") return { kind: "image", ext: "webp" };
  if (head.length >= 12 && text(head, 4, 8) === "ftyp" && HEIF.has(text(head, 8, 12))) return { kind: "image", ext: "heic" };
  if (startsText(head, "{\\rtf")) return { kind: "doc", ext: "rtf" };
  if (starts(head, [0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1])) return { kind: "doc", ext: "doc" };
  return null;
}

function extension(name) {
  const clean = String(name || "").trim().toLowerCase();
  const dot = clean.lastIndexOf(".");
  return dot < 0 ? "" : clean.slice(dot + 1);
}

function isZip(head) {
  return starts(head, [0x50, 0x4b, 0x03, 0x04]);
}

function starts(head, bytes) {
  if (head.length < bytes.length) return false;
  return bytes.every((byte, index) => head[index] === byte);
}

function startsText(head, value) {
  return text(head, 0, value.length) === value;
}

function text(head, from, to) {
  let value = "";
  for (let index = from; index < to && index < head.length; index += 1) value += String.fromCharCode(head[index]);
  return value;
}
