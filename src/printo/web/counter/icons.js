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

export function rotateIcon() {
  return svg(
    '<svg viewBox="0 0 24 24" aria-hidden="true">' +
    '<path d="M20 4.5v5.2h-5.2" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>' +
    '<path d="M19.6 9.5A8.2 8.2 0 1 0 20 14" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>' +
    '</svg>',
  );
}

export function clearIcon() {
  return svg('<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 3l6 6M9 3l-6 6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>');
}

export function landscapeIcon() {
  /* Two portrait pages side-by-side inside a landscape rectangle */
  return svg(
    '<svg viewBox="0 0 24 24" aria-hidden="true">' +
    '<rect x="1.8" y="4.5" width="20.4" height="15" rx="2" ry="2" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round"/>' +
    '<line x1="12" y1="6.5" x2="12" y2="17.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" opacity="0.55"/>' +
    '<rect x="3.5" y="6.5" width="6.8" height="11" rx="1" ry="1" fill="none" stroke="currentColor" stroke-width="1.2" opacity="0.45"/>' +
    '<rect x="13.7" y="6.5" width="6.8" height="11" rx="1" ry="1" fill="none" stroke="currentColor" stroke-width="1.2" opacity="0.45"/>' +
    '</svg>',
  );
}

function svg(markup) {
  const wrap = document.createElement("template");
  wrap.innerHTML = markup;
  return wrap.content.firstElementChild;
}
