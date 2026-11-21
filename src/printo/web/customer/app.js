/* The phone only sends one file and reads a number back. It never sees anyone else's files. */

const ACCEPT = ".pdf,.doc,.docx,.odt,.rtf,.jpg,.jpeg,.png,.webp,.gif,.bmp,.tif,.tiff,.heic,.heif,image/*,application/pdf";
const EMPTY = "That file is empty. Please choose the file again.";
const AGAIN = "Please try that again in a moment.";

let pending = null;
let sending = false;

function boot() {
  watchDrops();
  showIdle();
}

function watchDrops() {
  document.addEventListener("dragover", (event) => event.preventDefault());
  document.addEventListener("drop", (event) => {
    event.preventDefault();
    const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
    if (file) choose(file);
  });
}

function choose(file) {
  if (sending) return;
  if (!file || file.size === 0) { showError(EMPTY); return; }
  pending = file;
  showChosen(file);
}

function send() {
  if (sending || !pending) return;
  const file = pending;
  sending = true;
  showSending(file);
  const body = new FormData();
  body.append("file", file, file.name);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/upload");
  xhr.upload.addEventListener("progress", (event) => setProgress(event.lengthComputable ? event.loaded / event.total : null));
  xhr.addEventListener("load", () => finish(xhr));
  xhr.addEventListener("error", () => fail(AGAIN));
  xhr.addEventListener("abort", () => fail(AGAIN));
  xhr.send(body);
}

function finish(xhr) {
  const body = read(xhr);
  sending = false;
  if (xhr.status >= 200 && xhr.status < 300 && body.ok && body.number) { showDone(body.number, body.message || ""); return; }
  fail(body.message || AGAIN);
}

function fail(message) {
  sending = false;
  pending = null;
  showError(message);
}

function read(xhr) {
  try { return JSON.parse(xhr.responseText || "{}"); }
  catch { return {}; }
}

function showIdle() {
  const input = document.createElement("input");
  input.className = "file";
  input.type = "file";
  input.accept = ACCEPT;
  input.addEventListener("change", () => { const file = input.files && input.files[0]; if (file) choose(file); });
  const pick = el("label", { class: "pick" });
  pick.append(input, el("strong", { text: "Choose a file" }), el("span", { class: "quiet drop-hint", text: "You can also drop one here." }));
  pick.addEventListener("dragover", () => pick.classList.add("over"));
  pick.addEventListener("dragleave", () => pick.classList.remove("over"));
  mount([heading("Send a file"), el("p", { class: "quiet", text: "PDF, Word, or a photo. It goes straight to the counter." }), pick]);
}

function showChosen(file) {
  const actions = el("div", { class: "actions" });
  actions.append(el("button", { class: "go", text: "Send it", on: { click: send } }), el("button", { class: "texty", text: "Choose a different file", on: { click: showIdle } }));
  mount([heading("Ready to send"), el("p", { class: "name", text: file.name }), el("p", { class: "quiet", text: sizeOf(file.size) }), actions]);
}

function showSending(file) {
  const track = el("div", { class: "track busy", attrs: { id: "track" } });
  track.append(el("span", { attrs: { id: "bar" } }));
  mount([heading("Sending…"), el("p", { class: "name", text: file.name }), track]);
}

function setProgress(ratio) {
  const bar = document.getElementById("bar");
  const track = document.getElementById("track");
  if (!bar || !track || ratio == null) return;
  track.classList.remove("busy");
  bar.style.width = Math.max(4, Math.round(ratio * 100)) + "%";
}

function showDone(number, message) {
  const actions = el("div", { class: "actions" });
  actions.append(el("button", { class: "texty", text: "Send another", on: { click: () => { pending = null; showIdle(); } } }));
  mount([el("p", { class: "eyebrow", text: "Tell them this number" }), heading(number, "ticket"), el("p", { class: "quiet", text: message }), actions]);
}

function showError(message) {
  const actions = el("div", { class: "actions" });
  actions.append(el("button", { class: "go", text: "Try again", on: { click: showIdle } }));
  mount([heading("That didn't go through"), el("p", { class: "note", text: message }), actions]);
}

function mount(nodes) {
  const stage = document.getElementById("stage");
  stage.replaceChildren();
  for (const node of nodes) stage.append(node);
}

function heading(text, className) {
  return el("h1", { class: className || "", text: text });
}

function sizeOf(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + " KB";
  const mb = bytes / (1024 * 1024);
  return (mb >= 10 ? String(Math.round(mb)) : mb.toFixed(1)) + " MB";
}

function el(tag, props) {
  const node = document.createElement(tag);
  const options = props || {};
  if (options.class) node.className = options.class;
  if (options.text != null) node.textContent = options.text;
  if (options.attrs) for (const [key, value] of Object.entries(options.attrs)) node.setAttribute(key, value);
  if (options.on) for (const [key, fn] of Object.entries(options.on)) node.addEventListener(key, fn);
  if (tag === "button") node.type = "button";
  return node;
}

boot();
