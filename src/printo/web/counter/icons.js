/* Small marks for the counter. Built from our own markup, never from a file name. */

export function trashIcon() {
  return svg(
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.5 7h15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>' +
    '<path d="M9 7V5.6c0-.9.7-1.6 1.6-1.6h2.8c.9 0 1.6.7 1.6 1.6V7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>' +
    '<path d="M7 7.2 7.7 18.4A1.6 1.6 0 0 0 9.3 20h5.4a1.6 1.6 0 0 0 1.6-1.5L17 7.2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>' +
    '<path d="M10 10.5v6M14 10.5v6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  );
}

export function checkIcon() {
  return svg('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.2 8.3 6.4 11.4 12.8 4.7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>');
}

export function backIcon() {
  return svg('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3.5 5 8l5 4.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>');
}

function svg(markup) {
  const wrap = document.createElement("template");
  wrap.innerHTML = markup;
  return wrap.content.firstElementChild;
}
