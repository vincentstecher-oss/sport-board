// Sport Board Widget für Scriptable (iPhone)
// Liest die Daten aus deiner Sport-Board-App auf GitHub Pages.
// Größen: klein, mittel, groß, Sperrbildschirm (rechteckig + einzeilig).

const URL_APP = "https://vincentstecher-oss.github.io/sport-board/";
const CACHE = "sportboard-cache.json";

// ---------- Daten laden ----------
async function loadData() {
  const fm = FileManager.local();
  const path = fm.joinPath(fm.cacheDirectory(), CACHE);
  try {
    const req = new Request(URL_APP + "?t=" + Date.now());
    req.timeoutInterval = 15;
    const html = await req.loadString();
    const m = html.match(/<script type="application\/json" id="board-data">([\s\S]*?)<\/script>/);
    if (!m) throw new Error("Keine Daten gefunden");
    const data = JSON.parse(m[1]);
    fm.writeString(path, JSON.stringify(data));
    return { data, offline: false };
  } catch (e) {
    if (fm.fileExists(path)) return { data: JSON.parse(fm.readString(path)), offline: true };
    throw e;
  }
}

// ---------- Termine aufbereiten ----------
const ICON = { fussball: "⚽", tennis: "🎾", golf: "⛳", boxen: "🥊", mma: "🥋", f1: "🏎️" };

function dayStart(d) { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; }
function parseDay(s) { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); }

function buildList(data, now) {
  const today = dayStart(now);
  const out = [];
  for (const e of data.events || []) {
    let when, hasTime;
    if (e.start) { when = new Date(e.start); hasTime = true; }
    else if (e.date) { when = parseDay(e.date); hasTime = false; }
    else continue;
    const end = hasTime ? new Date(when.getTime() + (e.dur || 120) * 60000) : new Date(when.getTime() + 86400000);
    if (end < now) continue;
    out.push({ e, when, hasTime, day: dayStart(when) });
  }
  out.sort((a, b) => a.when - b.when || (b.e.bayern ? 1 : 0) - (a.e.bayern ? 1 : 0));
  const running = (data.series || []).filter(s => parseDay(s.from) <= today && parseDay(s.to) >= today);
  return { items: out, running };
}

function dayLabel(day, today) {
  const diff = Math.round((day - today) / 86400000);
  if (diff === 0) return "Heute";
  if (diff === 1) return "Morgen";
  const wd = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"][day.getDay()];
  return wd + " " + day.getDate() + "." + (day.getMonth() + 1) + ".";
}
function timeLabel(it) {
  if (!it.hasTime) return it.e.tent ? "tba" : "–";
  const f = new DateFormatter(); f.dateFormat = "HH:mm";
  return f.string(it.when) + (it.e.tent ? "?" : "");
}

// ---------- Farben ----------
const C = {
  bg: new Color("#080B10"), panel: new Color("#12161E"),
  text: new Color("#F2F4F7"), dim: new Color("#8A93A3"), faint: new Color("#5B6372"),
  bayern: new Color("#E0323C"), line: new Color("#222833"),
};

function addText(stack, str, size, color, weight) {
  const t = stack.addText(str);
  t.font = weight === "b" ? Font.boldSystemFont(size) : weight === "m" ? Font.mediumSystemFont(size) : Font.systemFont(size);
  t.textColor = color; t.lineLimit = 1; t.minimumScaleFactor = 0.7;
  return t;
}

function eventRow(parent, it, today, opts) {
  const row = parent.addStack(); row.centerAlignContent();
  row.spacing = 6;
  const color = it.e.bayern ? C.bayern : C.text;
  const t = row.addStack(); t.size = new Size(opts.timeW, 0);
  addText(t, timeLabel(it), opts.fs - 1, it.e.bayern ? C.bayern : C.dim, "m");
  addText(row, (ICON[it.e.sport] || "•") + " " + (it.e.short || it.e.home), opts.fs, color, "b");
  row.addSpacer();
  if (opts.showComp) addText(row, it.e.comp, opts.fs - 3, C.faint, "r");
  return row;
}

// ---------- Widgets ----------
function emptyHint(parent, text, size) { addText(parent, text, size, C.dim, "r"); }

function buildSmall(w, L, now) {
  const today = dayStart(now);
  const next = L.items.slice(0, 2);
  addText(w, "SPORT BOARD", 9, C.faint, "b");
  w.addSpacer(6);
  if (!next.length) { emptyHint(w, "Nichts angesetzt", 12); return; }
  next.forEach((it, i) => {
    if (i) w.addSpacer(8);
    addText(w, dayLabel(it.day, today) + (it.hasTime ? " · " + timeLabel(it) : ""), 10, it.e.bayern ? C.bayern : C.dim, "m");
    addText(w, (ICON[it.e.sport] || "") + " " + it.e.short, 15, C.text, "b");
    addText(w, it.e.comp, 9, C.faint, "r");
  });
}

function buildList_(w, L, now, maxRows, fs, multiDay) {
  const today = dayStart(now), T = today.getTime();
  const todays = L.items.filter(i => i.day.getTime() === T);
  const head = w.addStack(); head.centerAlignContent();
  addText(head, "SPORT BOARD", 9, C.faint, "b"); head.addSpacer();
  addText(head, todays.length ? "HEUTE · " + todays.length : "HEUTE FREI", 9, todays.length ? C.text : C.faint, "b");
  w.addSpacer(6);

  // laufende Turniere (Golf/Tennis) als eine Zeile
  if (L.running.length) {
    const r = L.running.map(s => (ICON[s.sport] || "") + " " + s.name).slice(0, 2).join("  ·  ");
    addText(w, "Läuft: " + r, fs - 2, C.dim, "r"); w.addSpacer(4); maxRows--;
  }

  // Gruppen nach Tag bilden
  const groups = [];
  for (const it of L.items) {
    const g = groups[groups.length - 1];
    if (g && g.day === it.day.getTime()) g.items.push(it); else groups.push({ day: it.day.getTime(), date: it.day, items: [it] });
  }
  // Mittel: nur der erste Tag (heute, sonst nächster Tag mit Hinweis). Groß: mehrere Tage.
  const shown = multiDay ? groups.slice(0, 4) : groups.slice(0, 1);
  if (!shown.length) { emptyHint(w, "Nichts angesetzt", fs); w.addSpacer(); return; }
  if (!todays.length) { addText(w, "Heute nichts angesetzt", fs - 1, C.dim, "r"); w.addSpacer(5); }

  let rows = 0, left = 0;
  for (const g of shown) {
    if (rows >= maxRows - 1) { left += g.items.length; continue; }
    if (multiDay || g.day !== T) {
      addText(w, dayLabel(g.date, today).toUpperCase() + (g.day === T ? "" : "  ·  " + g.items.length + (g.items.length === 1 ? " Spiel" : " Spiele")), fs - 3, g.day === T ? C.text : C.dim, "b");
      w.addSpacer(2); rows++;
    }
    for (let i = 0; i < g.items.length; i++) {
      if (rows >= maxRows) { left += g.items.length - i; break; }
      eventRow(w, g.items[i], today, { fs, timeW: fs * 3.4, showComp: true });
      w.addSpacer(3); rows++;
    }
    w.addSpacer(4);
  }
  if (left > 0) addText(w, "+ " + left + " weitere", fs - 3, C.faint, "m");
  w.addSpacer();
}

function buildLock(w, L, now, inline) {
  const today = dayStart(now);
  if (inline) {
    const it = L.items[0];
    addText(w, it ? (ICON[it.e.sport] || "") + " " + it.e.short + " " + dayLabel(it.day, today) + (it.hasTime ? " " + timeLabel(it) : "") : "Sport: nichts angesetzt", 12, Color.white(), "m");
    return;
  }
  L.items.slice(0, 3).forEach(it => {
    addText(w, (it.e.short) + "  " + dayLabel(it.day, today) + (it.hasTime ? " " + timeLabel(it) : ""), 12, Color.white(), "m");
  });
  if (!L.items.length) addText(w, "Nichts angesetzt", 12, Color.white(), "m");
}

async function main() {
  const fam = config.widgetFamily || "medium";
  const w = new ListWidget();
  w.url = URL_APP;
  const now = new Date();
  try {
    const { data, offline } = await loadData();
    const L = buildList(data, now);
    const lock = fam.startsWith("accessory");
    if (!lock) {
      w.backgroundColor = C.bg;
      w.setPadding(12, 14, 10, 14);
    }
    if (fam === "small") buildSmall(w, L, now); 
    else if (fam === "medium") buildList_(w, L, now, 5, 12, false);
    else if (fam === "large") buildList_(w, L, now, 14, 12, true);
    else if (fam === "extraLarge") buildList_(w, L, now, 14, 13, true);
    else if (fam === "accessoryInline") buildLock(w, L, now, true);
    else if (fam === "accessoryRectangular" || fam === "accessoryCircular") buildLock(w, L, now, false);
    else buildList_(w, L, now, 5, 12, false);
    if (offline && !lock) { w.addSpacer(); addText(w, "offline · Stand gespeichert", 8, C.faint, "r"); }
  } catch (e) {
    w.backgroundColor = C.bg;
    addText(w, "Sport Board", 12, C.text, "b");
    addText(w, "Keine Verbindung", 11, C.dim, "r");
  }
  w.refreshAfterDate = new Date(Date.now() + 30 * 60 * 1000);
  if (config.runsInWidget) Script.setWidget(w);
  else await w.presentLarge();
  Script.complete();
}

await main();
