/* Group files by the shop laptop's local year, month, and day.
   The current year, month, and day start open. Older ones stay closed until opened by hand. */

const MONTH = new Intl.DateTimeFormat("en", { month: "long" });
const WEEKDAY = new Intl.DateTimeFormat("en", { weekday: "long" });
const CLOCK = new Intl.DateTimeFormat("en", { hour: "numeric", minute: "2-digit" });

export function arrange(jobs, now) {
  const years = new Map();
  const ordered = jobs.slice().sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
  for (const job of ordered) place(years, job, slotOf(job.created_at, now));
  return [...years.values()].sort(newerFirst).map(finishYear);
}

export function isOpen(kind, key, folds, now) {
  const id = foldId(kind, key);
  if (folds.shut.has(id)) return false;
  if (folds.forced.has(id)) return true;
  return openByDefault(kind, key, now);
}

export function whenLabel(iso, now) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const seconds = Math.max(0, (now.getTime() - date.getTime()) / 1000);
  if (seconds < 45) return "Just now";
  if (seconds < 3600 && sameDay(date, now)) {
    const minutes = Math.max(1, Math.round(seconds / 60));
    return minutes === 1 ? "1 min ago" : minutes + " min ago";
  }
  return CLOCK.format(date);
}

function place(years, job, slot) {
  const year = ensure(years, slot.y, "year", slot.yearLabel, slot.yearSpoken);
  const month = ensure(year.kids, slot.m, "month", slot.monthLabel, slot.monthSpoken);
  const day = ensure(month.kids, slot.d, "day", slot.dayName, slot.daySpoken);
  day.dayNum = slot.dayNum;
  day.today = slot.today;
  day.jobs.push(job);
}

function ensure(map, key, kind, title, spoken) {
  let node = map.get(key);
  if (node) return node;
  node = { key, kind, title, spoken, dayNum: "", today: false, kids: new Map(), jobs: [] };
  map.set(key, node);
  return node;
}

function finishYear(year) {
  const months = [...year.kids.values()].sort(newerFirst).map(finishMonth);
  const jobs = months.flatMap((month) => month.children.flatMap((day) => day.jobs));
  return { ...present(year, jobs), children: months };
}

function finishMonth(month) {
  const days = [...month.kids.values()].sort(newerFirst).map((day) => ({ ...present(day, day.jobs), jobs: day.jobs }));
  const jobs = days.flatMap((day) => day.jobs);
  return { ...present(month, jobs), children: days };
}

function present(node, jobs) {
  let waiting = 0;
  for (const job of jobs) if (job.status !== "done") waiting += 1;
  return {
    id: foldId(node.kind, node.key), kind: node.kind, key: node.key, title: node.title, spoken: node.spoken,
    dayNum: node.dayNum || "", today: Boolean(node.today), total: jobs.length, waiting,
  };
}

function newerFirst(a, b) {
  if (a.key === "unknown") return 1;
  if (b.key === "unknown") return -1;
  return a.key < b.key ? 1 : a.key > b.key ? -1 : 0;
}

function slotOf(iso, now) {
  const date = new Date(iso || "");
  if (Number.isNaN(date.getTime())) return unknownSlot();
  const y = String(date.getFullYear());
  const m = y + "-" + pad(date.getMonth() + 1);
  const d = m + "-" + pad(date.getDate());
  const today = sameDay(date, now);
  const monthLabel = MONTH.format(date);
  const dayNum = String(date.getDate());
  const weekday = WEEKDAY.format(date);
  return {
    y, m, d, today, yearLabel: y, monthLabel, dayName: today ? "Today" : weekday, dayNum: today ? "" : dayNum,
    yearSpoken: y, monthSpoken: monthLabel + " " + y, daySpoken: today ? "Today" : weekday + " " + dayNum,
  };
}

function unknownSlot() {
  return {
    y: "unknown", m: "unknown", d: "unknown", today: false, yearLabel: "Other", monthLabel: "Other", dayName: "Other", dayNum: "",
    yearSpoken: "Other", monthSpoken: "Other", daySpoken: "Other",
  };
}

function openByDefault(kind, key, now) {
  const today = slotOf(now.toISOString(), now);
  if (kind === "year") return key === today.y;
  if (kind === "month") return key === today.m;
  return key === today.d;
}

function foldId(kind, key) { return kind[0] + ":" + key; }

function sameDay(date, now) {
  return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate();
}

function pad(value) { return String(value).padStart(2, "0"); }
