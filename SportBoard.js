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

function compLabel(e) {
  if (e.sport === "f1") return "Formel 1 · " + (e.away || "Rennen");
  return e.comp;
}

function eventRow(parent, it, fs) {
  const row = parent.addStack(); row.centerAlignContent();
  row.spacing = 6;
  const t = row.addStack(); t.size = new Size(Math.round(fs * 3.5), 0);
  addText(t, timeLabel(it), fs - 1, it.e.bayern ? C.bayern : C.dim, "m");
  addText(row, (ICON[it.e.sport] || "•") + " " + (it.e.short || it.e.home), fs, it.e.bayern ? C.bayern : C.text, "b");
  row.addSpacer();
  addText(row, compLabel(it.e), Math.max(fs - 4, 9), C.faint, "r");
  return row;
}

// ---------- Platz berechnen: Schrift so groß wie möglich ----------
function availHeight(fam) {
  let k = 1;
  try { k = Math.min(1.25, Math.max(0.9, Device.screenSize().width / 393)); } catch (e) {}
  const h = fam === "large" ? 354 : 158;           // Widget-Höhe in pt (iPhone ohne Max)
  return Math.round(h * k) - 22 - 18;              // minus Rand und Kopfzeile
}
const rowH = fs => fs * 1.25 + 3;

function layout(lines, avail, maxFs, minFs) {
  // lines: {k:"ev"|"hdr"|"run"|"more", ...}; Höhe je Typ
  const total = fs => lines.reduce((a, l) => a + (l.k === "ev" ? rowH(fs) : rowH(fs - 4)), 0);
  let moreCount = 0;
  while (total(minFs) > avail && lines.filter(l => l.k === "ev").length > 1) {
    const last = lines.pop();
    if (last.k === "ev") moreCount++;
    while (lines.length && lines[lines.length - 1].k === "hdr") lines.pop();   // keine Überschrift ohne Zeilen
  }
  if (moreCount) lines.push({ k: "more", text: "+ " + moreCount + " weitere" });
  let fs = maxFs;
  while (fs > minFs && total(fs) > avail) fs--;
  const gap = Math.max(2, Math.min(10, (avail - total(fs)) / Math.max(1, lines.length)));
  return { fs, gap, lines };
}

// ---------- Widgets ----------
function emptyHint(parent, text, size) { addText(parent, text, size, C.dim, "r"); }

function header(w, todays) {
  const head = w.addStack(); head.centerAlignContent();
  addText(head, "SPORT BOARD", 9, C.faint, "b"); head.addSpacer();
  addText(head, todays ? "HEUTE · " + todays : "HEUTE FREI", 9, todays ? C.text : C.faint, "b");
  w.addSpacer(6);
}

function buildSmall(w, L, now) {
  const today = dayStart(now);
  addText(w, "SPORT BOARD", 9, C.faint, "b");
  w.addSpacer(8);
  const next = L.items.slice(0, 2);
  if (!next.length) { emptyHint(w, "Nichts angesetzt", 13); w.addSpacer(); return; }
  next.forEach((it, i) => {
    if (i) w.addSpacer(12);
    addText(w, dayLabel(it.day, today).toUpperCase() + (it.hasTime ? " · " + timeLabel(it) : ""), 11, it.e.bayern ? C.bayern : C.dim, "b");
    addText(w, (ICON[it.e.sport] || "") + " " + it.e.short, 18, it.e.bayern ? C.bayern : C.text, "b");
    addText(w, compLabel(it.e), 10, C.faint, "r");
  });
  w.addSpacer();
}

function buildList_(w, L, now, fam) {
  const today = dayStart(now), T = today.getTime();
  const multi = fam === "large";
  const todays = L.items.filter(i => i.day.getTime() === T).length;
  header(w, todays);

  const groups = [];
  for (const it of L.items) {
    const g = groups[groups.length - 1];
    if (g && g.day === it.day.getTime()) g.items.push(it); else groups.push({ day: it.day.getTime(), date: it.day, items: [it] });
  }
  const shown = multi ? groups.slice(0, 4) : groups.slice(0, 1);
  const lines = [];
  if (L.running.length) lines.push({ k: "run", text: "Läuft: " + L.running.map(s => (ICON[s.sport] || "") + " " + s.name).slice(0, 2).join("  ·  ") });
  if (!todays) lines.push({ k: "hdr", text: "Heute nichts angesetzt", dim: true });
  for (const g of shown) {
    if (multi || g.day !== T) lines.push({ k: "hdr", text: dayLabel(g.date, today).toUpperCase() + (g.day === T ? "" : "  ·  " + g.items.length + (g.items.length === 1 ? " Spiel" : " Spiele")), dim: g.day !== T });
    g.items.forEach(it => lines.push({ k: "ev", it }));
  }
  if (!shown.length) lines.push({ k: "hdr", text: "Nichts angesetzt", dim: true });

  const { fs, gap, lines: L2 } = layout(lines, availHeight(fam), multi ? 15 : 19, 10);
  for (const l of L2) {
    if (l.k === "ev") eventRow(w, l.it, fs);
    else if (l.k === "run") addText(w, l.text, fs - 3, C.dim, "r");
    else if (l.k === "more") addText(w, l.text, fs - 4, C.faint, "m");
    else addText(w, l.text, fs - 4, l.dim ? C.dim : C.text, "b");
    w.addSpacer(gap);
  }
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
  let fam = config.widgetFamily;
  if (!fam) {   // in der App gestartet: Größe zur Vorschau wählen
    const a = new Alert(); a.title = "Vorschau";
    ["Klein", "Mittel", "Groß"].forEach(x => a.addAction(x));
    a.addCancelAction("Abbrechen");
    const i = await a.presentSheet();
    fam = ["small", "medium", "large"][i];
    if (!fam) { Script.complete(); return; }
  }
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
    else if (fam === "medium") buildList_(w, L, now, "medium");
    else if (fam === "large" || fam === "extraLarge") buildList_(w, L, now, "large");
    else if (fam === "accessoryInline") buildLock(w, L, now, true);
    else if (fam === "accessoryRectangular" || fam === "accessoryCircular") buildLock(w, L, now, false);
    else buildList_(w, L, now, "medium");
    if (offline && !lock) addText(w, "offline · Stand gespeichert", 8, C.faint, "r");
  } catch (e) {
    w.backgroundColor = C.bg;
    addText(w, "Sport Board", 12, C.text, "b");
    addText(w, "Keine Verbindung", 11, C.dim, "r");
  }
  w.refreshAfterDate = new Date(Date.now() + 30 * 60 * 1000);
  if (config.runsInWidget) Script.setWidget(w);
  else if (fam === "small") await w.presentSmall();
  else if (fam === "medium") await w.presentMedium();
  else await w.presentLarge();
  Script.complete();
}

await main();
