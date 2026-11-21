import { icon } from "./dom.js";

const DOC = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3.5h6.2L18 8.2V19a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 19V5A1.5 1.5 0 0 1 7.5 3.5H7z" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M13 3.8V8h4.2" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>';

export function fileIcon() {
  return icon(DOC);
}

export function closeIcon() {
  return icon('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7l10 10M17 7 7 17" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/></svg>');
}

export function checkIcon() {
  return icon('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.2 8.2 6.4 11.4 12.8 4.6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>');
}

export function plusIcon() {
  return icon('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/></svg>');
}

export function minusIcon() {
  return icon('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 12h12" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/></svg>');
}
