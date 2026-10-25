// Sport Board – Widget für Übersicht (macOS-Schreibtisch), mittlere Apple-Widget-Größe, nur heute.
// Installation: Datei in den Widget-Ordner von Übersicht legen (Menüleiste: Übersicht > Open Widgets Folder).
// Position: sitzt links unter den Apple-Widgets Uhr und Kalender (gemessen auf Vincents MacBook: Apple-Widgets
// 14 pt vom linken Rand, Abstand 16 pt, kleine Widgets enden 595 pt unter der Bildschirmoberkante;
// Übersicht zählt ab Unterkante der Menüleiste, daher top 572). Zum Verschieben top/left ändern.
import { run } from "uebersicht";

const URL_APP = "https://vincentstecher-oss.github.io/sport-board/";
export const command = `curl -sfL --max-time 20 "${URL_APP}?w=$(date +%s)"`;
export const refreshFrequency = 5 * 60 * 1000;

export const className = `
  top: 572px;
  left: 14px;
  width: 344px;
  height: 164px;
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
  color: #F2F4F7;
  -webkit-font-smoothing: antialiased;
`;

// ---------- Daten ----------
const TZ = "Europe/Berlin";
const fDay = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const fTime = new Intl.DateTimeFormat("de-DE", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const fHead = new Intl.DateTimeFormat("de-DE", { timeZone: TZ, weekday: "long", day: "numeric", month: "long" });
const fDow = new Intl.DateTimeFormat("de-DE", { timeZone: "UTC", weekday: "short" });
const SPORT = { fussball: "Fußball", tennis: "Tennis", golf: "Golf", boxen: "Boxen", mma: "MMA", f1: "Formel 1" };
const MAX_ROWS = 3;

const norm = (s) => String(s || "").toLowerCase().replace(/\s+/g, " ").trim();
const keyDate = (k) => new Date(k + "T12:00:00Z");

export function parse(output) {
  const m = String(output || "").match(/<script type="application\/json" id="board-data">([\s\S]*?)<\/script>/);
  return m ? JSON.parse(m[1]) : null;
}

export function model(data, now) {
  const today = fDay.format(now);
  const results = {};
  (data.fixtures || []).forEach((f) => f.rounds.forEach((r) => r.m.forEach((m) => {
    if (!m[3]) return;
    const ts = m[0];
    const k = ts.length >= 10
      ? fDay.format(new Date(Date.UTC(2000 + +ts.slice(0, 2), +ts.slice(2, 4) - 1, +ts.slice(4, 6), +ts.slice(6, 8), +ts.slice(8, 10))))
      : "20" + ts.slice(0, 2) + "-" + ts.slice(2, 4) + "-" + ts.slice(4, 6);
    results[k + "|" + norm(f.teams[m[1]]) + "|" + norm(f.teams[m[2]])] = m[3].replace("-", ":");
  })));
  const all = (data.events || []).map((e) => {
    const o = { ...e };
    if (e.start) { o.t0 = new Date(e.start); o.t1 = new Date(o.t0.getTime() + (e.dur || 120) * 60000); o.key = fDay.format(o.t0); o.timed = true; }
    else { o.key = e.date; o.timed = false; }
    o.live = o.timed && !e.result && o.t0 <= now && now < o.t1;
    o.done = !o.live && (o.timed ? o.t1 <= now : false);
    const isScore = e.result && /^\d+\s*[-:]\s*\d+/.test(e.result);
    o.score = isScore ? e.result.replace(/\s+/g, "").replace("-", ":") : e.sport === "fussball" ? results[o.key + "|" + norm(e.home) + "|" + norm(e.away)] || "" : "";
    o.res = e.result && !isScore ? e.result : "";
    o.time = o.timed ? (e.tent ? "~" : "") + fTime.format(o.t0) : "offen";
    o.plain = e.comp === "DFB-Pokal" && !e.bayern && e.why !== "Top-4-Team";
    return o;
  }).filter((o) => o.key);
  const sorter = (a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : (a.timed === b.timed ? (a.timed ? a.t0 - b.t0 : 0) : a.timed ? -1 : 1));
  const list = all.filter((e) => e.key === today).sort(sorter);

  // Reihenfolge: Bayern, läuft gerade, kommt noch, vorbei
  const rank = (e) => (e.bayern && !e.done ? 0 : e.live ? 1 : !e.done ? 2 : 3);
  const ordered = list.slice().sort((a, b) => rank(a) - rank(b) || sorter(a, b));
  const plain = ordered.filter((e) => e.plain);
  const rows = [];
  let grouped = false;
  ordered.forEach((e) => {
    if (e.plain && plain.length > 2) {
      if (!grouped) { grouped = true; rows.push({ group: { n: plain.length, times: [...new Set(plain.map((p) => p.time))].sort().join(" / "), note: plain[0].note || "" } }); }
      return;
    }
    rows.push({ ev: e });
  });
  const running = (data.series || []).filter((s) => s.from <= today && today <= s.to);
  running.forEach((s) => rows.push({ series: s }));

  let next = null;
  if (!rows.length) {
    const fut = all.filter((e) => e.key > today).sort(sorter);
    const day = fut.length ? fut[0].key : null;
    const sameDay = fut.filter((e) => e.key === day);
    const n = sameDay.find((e) => e.bayern) || sameDay.find((e) => !e.plain) || sameDay[0];
    if (n) next = { e: n, when: `${fDow.format(keyDate(n.key)).replace(".", "")} ${+n.key.slice(8)}.${+n.key.slice(5, 7)}.${n.timed ? " " + n.time : ""}` };
  }
  const asOf = data.asOf ? new Date(data.asOf) : null;
  return {
    head: fHead.format(now),
    rows: rows.slice(0, MAX_ROWS),
    more: Math.max(0, rows.length - MAX_ROWS),
    count: list.length,
    next,
    old: asOf ? now - asOf > 26 * 3600000 : true,
  };
}

// ---------- Darstellung ----------
const C = { muted: "rgba(235,240,247,0.55)", line: "rgba(255,255,255,0.08)", fcb: "#FF4D5E", live: "#FF453A" };
const S = {
  card: {
    boxSizing: "border-box", width: 344, height: 164, padding: "13px 16px 12px", borderRadius: 22, overflow: "hidden", cursor: "pointer",
    color: "#F2F4F7", background: "rgba(28,30,36,0.78)", backdropFilter: "blur(30px) saturate(1.4)", WebkitBackdropFilter: "blur(30px) saturate(1.4)",
    boxShadow: "0 6px 24px rgba(0,0,0,0.25), inset 0 0 0 0.5px rgba(255,255,255,0.12)", display: "flex", flexDirection: "column",
  },
  head: { display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 },
  title: { fontSize: 13, fontWeight: 700, color: "#F2F4F7", letterSpacing: "0.01em" },
  date: { fontSize: 12, fontWeight: 500, color: C.muted },
  row: { display: "grid", gridTemplateColumns: "42px minmax(0,1fr) auto", columnGap: 8, alignItems: "center", height: 32, borderTop: `0.5px solid ${C.line}` },
  time: { fontSize: 13, fontWeight: 600, fontVariantNumeric: "tabular-nums" },
  name: { fontSize: 13, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", lineHeight: "16px" },
  sub: { fontSize: 11, fontWeight: 500, color: C.muted, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", lineHeight: "13px" },
  right: { fontSize: 12.5, fontWeight: 700, fontVariantNumeric: "tabular-nums" },
};

const label = (e) => (e.sport === "f1" ? `${e.home.replace("Großer Preis", "GP")} · ${e.away}` : `${e.home} – ${e.away}`);
const subOf = (e) => (e.sport === "f1" ? "Formel 1" + (e.place ? " · " + e.place : "") : (e.sport === "fussball" ? "" : SPORT[e.sport] + " · ") + e.comp);

function Row({ r, first }) {
  const st = { ...S.row, borderTop: first ? "none" : S.row.borderTop };
  if (r.group) {
    return (
      <div style={st}>
        <span style={{ ...S.time, color: C.muted }}>{r.group.n}×</span>
        <div style={{ minWidth: 0 }}><div style={S.name}>DFB-Pokal{r.group.note ? ", " + r.group.note : ""}</div><div style={S.sub}>{r.group.times}</div></div>
        <span />
      </div>
    );
  }
  if (r.series) {
    return (
      <div style={st}>
        <span style={{ ...S.time, color: C.muted }}>läuft</span>
        <div style={{ minWidth: 0 }}><div style={S.name}>{r.series.name}</div><div style={S.sub}>{SPORT[r.series.sport]}{r.series.place ? " · " + r.series.place : ""}</div></div>
        <span />
      </div>
    );
  }
  const e = r.ev;
  const dim = e.done && !e.score && !e.res;
  return (
    <div style={{ ...st, opacity: dim ? 0.45 : 1 }}>
      <span style={{ ...S.time, color: e.bayern ? C.fcb : "#F2F4F7" }}>{e.time}</span>
      <div style={{ minWidth: 0 }}><div style={S.name}>{label(e)}</div><div style={{ ...S.sub, color: e.res ? "#F2F4F7" : e.bayern ? C.fcb : C.muted }}>{e.res || subOf(e)}</div></div>
      <span style={{ ...S.right, color: e.live ? C.live : "#F2F4F7" }}>{e.live ? (e.score || "LIVE") : e.score}</span>
    </div>
  );
}

export const render = ({ output }) => {
  let m = null;
  try { const d = parse(output); if (d) m = model(d, new Date()); } catch (e) { m = null; }
  const open = () => run(`open "${URL_APP}"`);
  if (!m) {
    return (
      <div style={S.card} onClick={open}>
        <div style={S.head}><span style={S.title}>Sport heute</span></div>
        <div style={{ ...S.sub, fontSize: 12.5 }}>Keine Verbindung. Das Widget versucht es in ein paar Minuten wieder.</div>
      </div>
    );
  }
  return (
    <div style={S.card} onClick={open}>
      <div style={S.head}>
        <span style={S.title}>Sport heute{m.old ? <span style={{ color: C.muted, fontWeight: 500 }}> · alter Stand</span> : ""}</span>
        <span style={S.date}>{m.head}</span>
      </div>
      {m.rows.length ? (
        <div style={{ display: "flex", flexDirection: "column" }}>
          {m.rows.map((r, i) => <Row key={i} r={r} first={i === 0} />)}
          {m.more > 0 && <div style={{ ...S.sub, paddingTop: 3 }}>+ {m.more} weitere im Board</div>}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", flex: 1, gap: 6 }}>
          <div style={{ fontSize: 17, fontWeight: 700 }}>Heute nichts</div>
          {m.next && <div style={S.sub}>Als Nächstes: {m.next.when} · {label(m.next.e)}</div>}
        </div>
      )}
    </div>
  );
};
