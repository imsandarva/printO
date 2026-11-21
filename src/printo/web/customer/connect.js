/* The page loaded, so we start connected. A quiet check keeps that honest. */

const WAIT = 4000;
const EVERY = 8000;

export function watchShop(onChange) {
  let timer = 0;
  async function ping() {
    const control = new AbortController();
    const kill = setTimeout(() => control.abort(), WAIT);
    try {
      const response = await fetch("/shop", { cache: "no-store", signal: control.signal });
      const body = await response.json();
      onChange(Boolean(response.ok && body.ok), body.name || "");
    } catch {
      onChange(false, "");
    } finally {
      clearTimeout(kill);
    }
  }
  timer = setInterval(ping, EVERY);
  window.addEventListener("online", ping);
  window.addEventListener("offline", () => onChange(false, ""));
  document.addEventListener("visibilitychange", () => { if (!document.hidden) ping(); });
  ping();
  return () => clearInterval(timer);
}
