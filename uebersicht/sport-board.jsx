// Sport Board – Widget für Übersicht (macOS-Schreibtisch)
// Installation: Datei in den Widget-Ordner von Übersicht legen (Menüleiste: Übersicht > Open Widgets Folder).
// Liest die Daten aus https://vincentstecher-oss.github.io/sport-board/ und zeigt Bayern, heute und die nächsten Tage.
// Position anpassen: unten bei className die Werte top/right ändern.
import { run } from "uebersicht";

const URL_APP = "https://vincentstecher-oss.github.io/sport-board/";
export const command = `curl -sfL --max-time 20 "${URL_APP}?w=$(date +%s)"`;
export const refreshFrequency = 10 * 60 * 1000;

export const className = `
  top: 36px;
  right: 28px;
  width: 330px;
  font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif;
  color: #EEF1F5;
  -webkit-font-smoothing: antialiased;
`;

// ---------- Daten aufbereiten ----------
const TZ = "Europe/Berlin";
const fDay = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const fTime = new Intl.DateTimeFormat("de-DE", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const fDow = new Intl.DateTimeFormat("de-DE", { timeZone: "UTC", weekday: "short" });
const SPORT = { fussball: "Fußball", tennis: "Tennis", golf: "Golf", boxen: "Boxen", mma: "MMA", f1: "Formel 1" };

const keyDate = (k) => new Date(k + "T12:00:00Z");
const diffDays = (a, b) => Math.round((keyDate(b) - keyDate(a)) / 86400000);
const norm = (s) => String(s || "").toLowerCase().replace(/\s+/g, " ").trim();

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
  const evs = (data.events || []).map((e) => {
    const o = { ...e };
    if (e.start) { o.t0 = new Date(e.start); o.t1 = new Date(o.t0.getTime() + (e.dur || 120) * 60000); o.key = fDay.format(o.t0); o.timed = true; }
    else { o.key = e.date; o.timed = false; }
    o.live = o.timed && o.t0 <= now && now < o.t1;
    o.done = o.timed ? o.t1 <= now : o.key < today;
    o.score = e.sport === "fussball" ? results[o.key + "|" + norm(e.home) + "|" + norm(e.away)] || "" : "";
    o.time = o.timed ? (e.tent ? "~" : "") + fTime.format(o.t0) : "offen";
    o.plain = e.comp === "DFB-Pokal" && !e.bayern && e.why !== "Top-4-Team";
    return o;
  }).filter((o) => o.key).sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : (a.timed === b.timed ? (a.timed ? a.t0 - b.t0 : 0) : a.timed ? -1 : 1)));

  const fcb = evs.find((e) => e.bayern && !e.done && diffDays(today, e.key) <= 10) || null;
  if (fcb) {
    const d = diffDays(today, fcb.key), mins = fcb.timed ? Math.round((fcb.t0 - now) / 60000) : null;
    fcb.rel = fcb.live ? "läuft" : d === 0 ? (mins !== null && mins < 60 ? `in ${Math.max(1, mins)} Min` : "heute") : d === 1 ? "morgen" : `${fDow.format(keyDate(fcb.key)).replace(".", "")} ${+fcb.key.slice(8)}.${+fcb.key.slice(5, 7)}.`;
  }
  const rows = (list) => {
    const plain = list.filter((e) => e.plain);
    if (plain.length <= 3) return list.map((e) => ({ ev: e }));
    const out = []; let added = false;
    list.forEach((e) => {
      if (!e.plain) { out.push({ ev: e }); return; }
      if (!added) { added = true; out.push({ group: { n: plain.length, times: [...new Set(plain.map((p) => p.time))].sort().join(" / "), note: plain[0].note || "" } }); }
    });
    return out;
  };
  const todayList = evs.filter((e) => e.key === today && (!fcb || e.id !== fcb.id));
  const days = [];
  for (let i = 1; i <= 7 && days.length < 3; i++) {
    const k = fDay.format(new Date(keyDate(today).getTime() + i * 86400000));
    const list = evs.filter((e) => e.key === k && (!fcb || e.id !== fcb.id));
    if (list.length) days.push({ label: i === 1 ? "Morgen" : `${fDow.format(keyDate(k)).replace(".", "")} ${+k.slice(8)}.${+k.slice(5, 7)}.`, rows: rows(list) });
  }
  const running = (data.series || []).filter((s) => s.from <= today && today <= s.to);
  const asOf = data.asOf ? new Date(data.asOf) : null;
  return {
    fcb, today: rows(todayList), days, running,
    stamp: asOf ? "Stand " + (fDay.format(asOf) === today ? fTime.format(asOf) : `${+fDay.format(asOf).slice(8)}.${+fDay.format(asOf).slice(5, 7)}.`) : "",
    old: asOf ? now - asOf > 26 * 3600000 : true,
  };
}

// ---------- Darstellung ----------
const C = { card: "rgba(14,17,23,0.86)", line: "rgba(236,241,248,0.08)", muted: "#8F98A6", faint: "#5D6674", fcb: "#DC2B3A", fcbInk: "#F39AA3", live: "#FF4B5C" };
const S = {
  card: { color: "#EEF1F5", background: C.card, border: `1px solid ${C.line}`, borderRadius: 18, padding: "14px 14px 10px", backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)", boxShadow: "0 12px 34px rgba(0,0,0,0.35)", cursor: "pointer" },
  head: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 },
  brand: { fontSize: 11, fontWeight: 800, letterSpacing: "0.12em", color: C.muted },
  stamp: { fontSize: 11, color: C.faint, display: "flex", alignItems: "center", gap: 6 },
  label: { fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: C.muted, margin: "10px 0 4px" },
  row: { display: "grid", gridTemplateColumns: "46px 1fr auto", gap: 8, alignItems: "baseline", padding: "5px 0", borderTop: `1px solid ${C.line}` },
  time: { fontSize: 14, fontWeight: 700, fontVariantNumeric: "tabular-nums" },
  title: { fontSize: 13.5, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" },
  sub: { fontSize: 11.5, color: C.muted, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" },
  right: { fontSize: 13, fontWeight: 700, fontVariantNumeric: "tabular-nums" },
  fcb: { borderRadius: 14, padding: "10px 12px", background: "linear-gradient(135deg, rgba(220,43,58,0.22), rgba(220,43,58,0.06))", border: "1px solid rgba(220,43,58,0.35)" },
};

const title = (e) => (e.sport === "f1" ? `${e.home.replace("Großer Preis", "GP")} · ${e.away}` : `${e.home} – ${e.away}`);
const sub = (e) => (e.sport === "f1" ? e.place || "Formel 1" : (e.sport === "boxen" || e.sport === "mma" ? SPORT[e.sport] + " · " : "") + e.comp + (e.bayern ? "" : e.why && e.why !== e.comp ? " · " + e.why : ""));

function Row({ r }) {
  if (r.group) {
    return (
      <div style={S.row}>
        <span style={{ ...S.time, color: C.muted }}>{r.group.n}×</span>
        <div style={{ minWidth: 0 }}><div style={S.title}>DFB-Pokal, weitere Spiele</div><div style={S.sub}>{r.group.times}{r.group.note ? " · " + r.group.note : ""}</div></div>
        <span />
      </div>
    );
  }
  const e = r.ev;
  return (
    <div style={{ ...S.row, opacity: e.done && !e.score ? 0.5 : 1 }}>
      <span style={{ ...S.time, color: e.bayern ? C.fcbInk : "#EEF1F5" }}>{e.time}</span>
      <div style={{ minWidth: 0 }}><div style={S.title}>{title(e)}</div><div style={{ ...S.sub, color: e.bayern ? C.fcbInk : C.muted }}>{sub(e)}</div></div>
      <span style={{ ...S.right, color: e.live ? C.live : "#EEF1F5" }}>{e.live ? "LIVE" : e.score}</span>
    </div>
  );
}

export const render = ({ output, error }) => {
  let m = null;
  try { const d = parse(output); if (d) m = model(d, new Date()); } catch (e) { m = null; }
  const open = () => run(`open "${URL_APP}"`);
  if (!m) {
    return <div style={S.card} onClick={open}><div style={S.brand}>SPORT BOARD</div><div style={{ ...S.sub, marginTop: 6 }}>Keine Verbindung, versuche es gleich wieder.</div></div>;
  }
  return (
    <div style={S.card} onClick={open}>
      <div style={S.head}>
        <span style={S.brand}>SPORT BOARD</span>
        <span style={S.stamp}><i style={{ width: 6, height: 6, borderRadius: 3, background: m.old ? "#E2B24C" : "#5BC48D", display: "inline-block" }} />{m.stamp}</span>
      </div>
      {m.fcb && (
        <div style={S.fcb}>
          <div style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: "0.1em", color: C.fcbInk }}>FC BAYERN · {m.fcb.comp.toUpperCase()}</div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 10, marginTop: 6 }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ ...S.title, fontSize: 15, fontWeight: 700 }}>{m.fcb.home}</div>
              <div style={{ ...S.title, fontSize: 15, fontWeight: 700 }}>{m.fcb.away}</div>
            </div>
            <div style={{ textAlign: "right", flex: "none" }}>
              <div style={{ fontSize: 22, fontWeight: 800, fontVariantNumeric: "tabular-nums", color: m.fcb.live ? C.live : "#EEF1F5" }}>{m.fcb.live ? "LIVE" : m.fcb.time}</div>
              <div style={{ fontSize: 11.5, color: C.muted }}>{m.fcb.rel}</div>
            </div>
          </div>
        </div>
      )}
      <div style={S.label}>HEUTE</div>
      {m.today.length ? m.today.map((r, i) => <Row key={"t" + i} r={r} />) : <div style={{ ...S.sub, padding: "4px 0" }}>Heute steht {m.fcb && m.fcb.rel !== "morgen" && m.fcb.key === fDay.format(new Date()) ? "sonst " : ""}nichts an.</div>}
      {m.running.length > 0 && <div style={{ ...S.sub, paddingTop: 6 }}>Läuft: {m.running.map((s) => s.name).join(", ")}</div>}
      {m.days.map((d) => (
        <div key={d.label}>
          <div style={S.label}>{d.label.toUpperCase()}</div>
          {d.rows.map((r, i) => <Row key={d.label + i} r={r} />)}
        </div>
      ))}
    </div>
  );
};
