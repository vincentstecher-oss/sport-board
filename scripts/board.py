#!/usr/bin/env python3
"""Werkzeug für die Daten des Sport Boards (Datenblock board-data in index.html).

Befehle:
  python3 scripts/board.py push              Push-Text für heute ausgeben (oder NICHTS)
  python3 scripts/board.py status            Kurzer Lagebericht: laufende Turniere, Pokal, nächste Termine
  python3 scripts/board.py show SPORT        Termine einer Sportart kompakt auflisten (fussball, tennis, golf, boxen, mma, f1)
  python3 scripts/board.py apply PATCH.json  Änderungen einspielen (siehe PATCH-FORMAT unten)

PATCH-FORMAT (alle Schlüssel optional):
  {"upsert_events": [event, ...],        # gleiches id ersetzt, neues id wird angehängt
   "remove_events": ["id", ...],
   "upsert_series": [series, ...],
   "remove_series": ["id", ...],
   "notes": ["...", ...],                 # ersetzt die Hinweisliste komplett
   "set_notes": {"Präfix": "neuer Text oder leer zum Löschen"},   # einzelne Hinweise per Anfang ersetzen
   "pk_round": {"n": 2, "m": [["YYMMDDHHMM", "Heim", "Gast", "", 0], ...]},   # DFB-Pokal-Runde mit Teamnamen
   "pk_results": [["Heim", "Gast", "2-1"], ...]}

Die Datei wird kompakt und unverändert formatiert zurückgeschrieben; alles außerhalb des Datenblocks bleibt gleich.
"""
import json, re, sys, pathlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / 'index.html'
BERLIN = ZoneInfo('Europe/Berlin')
RX = re.compile(r'(<script type="application/json" id="board-data">)([\s\S]*?)(</script>)')
SPORTS = {'fussball', 'tennis', 'golf', 'boxen', 'mma', 'f1'}
SNAME = {'fussball': 'Fußball', 'tennis': 'Tennis', 'golf': 'Golf', 'boxen': 'Boxen', 'mma': 'MMA', 'f1': 'Formel 1'}


def load(path=INDEX):
    html = pathlib.Path(path).read_text(encoding='utf-8')
    m = RX.search(html)
    if not m:
        sys.exit('Datenblock board-data nicht gefunden')
    return html, json.loads(m.group(2))


def save(data, html, path=INDEX):
    text = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    json.loads(text)
    m = RX.search(html)
    new = html[:m.start(2)] + text + html[m.end(2):]
    changed = new != html
    if changed:
        pathlib.Path(path).write_text(new, encoding='utf-8')
    return changed


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def ev_day(e):
    if e.get('start'):
        return datetime.fromisoformat(e['start'].replace('Z', '+00:00')).astimezone(BERLIN).date()
    return datetime.strptime(e['date'], '%Y-%m-%d').date()


def ev_dt(e):
    if e.get('start'):
        return datetime.fromisoformat(e['start'].replace('Z', '+00:00')).astimezone(BERLIN)
    return None


def sort_key(e):
    d = ev_day(e)
    t = ev_dt(e)
    return (d.isoformat(), 0 if t else 1, t.strftime('%H:%M') if t else '', 0 if e.get('bayern') else 1)


def today_berlin():
    return now_utc().astimezone(BERLIN).date()


# ---------- Push-Text ----------
def push_text(data, day=None):
    day = day or today_berlin()
    evs = sorted([e for e in data.get('events', []) if ev_day(e) == day], key=sort_key)
    sers = [s for s in data.get('series', []) if s['from'] <= day.isoformat() <= s['to']]
    if not evs and not sers:
        return None

    def t(e):
        dt = ev_dt(e)
        return (('ca. ' if e.get('tent') else '') + dt.strftime('%H:%M')) if dt else 'Zeit offen'

    def line(e):
        if e['sport'] == 'f1':
            return f"{t(e)} {e['home']}, {e['away']}"
        return f"{t(e)} {e['home']} – {e['away']} ({e['comp']})"

    bayern = [e for e in evs if e.get('bayern')]
    rest = [e for e in evs if not e.get('bayern')]
    # Viele Pokalspiele ohne besondere Marke bündeln
    pk = [e for e in rest if e['comp'] == 'DFB-Pokal']
    lines = [line(e) for e in bayern]
    if len(pk) > 2:
        times = sorted({t(e) for e in pk})
        top = [e for e in pk if e.get('why') == 'Top-4-Team']
        rnd = pk[0].get('note', '')
        hint = f", u. a. {top[0]['short']}" if top else ''
        lines.append(f"DFB-Pokal{(' ' + rnd) if rnd else ''}: {len(pk)} Spiele, {' und '.join(times)}{hint}")
        rest = [e for e in rest if e not in pk]
    lines += [line(e) for e in rest]
    if len(lines) > 3 and sers:
        lines = lines[:2] + [f"+ {len(lines) - 2} weitere Termine im Board"]
    elif len(lines) > 4:
        lines = lines[:3] + [f"+ {len(lines) - 3} weitere Termine im Board"]
    if sers:
        lines.append('Läuft: ' + ', '.join(f"{s['name']} ({SNAME[s['sport']]})" for s in sers))
    return '\n'.join(lines[:4])


# ---------- Lagebericht für die Claude-Läufe ----------
def status(data):
    day = today_berlin()
    out = [f"Heute (Berlin): {day.isoformat()}  Stand der Daten: {data.get('asOf')}"]
    run = [s for s in data.get('series', []) if s['from'] <= day.isoformat() <= s['to']]
    soon = [s for s in data.get('series', []) if day.isoformat() < s['from'] <= (day + timedelta(days=3)).isoformat()]
    out.append('Laufende Turniere: ' + (', '.join(f"{s['id']} {s['name']} ({s['sport']}, bis {s['to']})" for s in run) or 'keine'))
    out.append('Turniere ab den nächsten 3 Tagen: ' + (', '.join(f"{s['id']} {s['name']} ({s['sport']}, ab {s['from']})" for s in soon) or 'keine'))
    pk = [e for e in data.get('events', []) if e['comp'] == 'DFB-Pokal']
    y = day - timedelta(days=1)
    out.append('DFB-Pokal gestern gespielt: ' + ('ja, Ergebnisse nachtragen' if any(ev_day(e) == y for e in pk) else 'nein'))
    out.append('DFB-Pokal-Termine im Board: ' + (', '.join(sorted({ev_day(e).isoformat() + ' ' + e.get('note', '') for e in pk})) or 'keine'))
    return '\n'.join(out)


def show(data, sport):
    rows = []
    for e in sorted([e for e in data.get('events', []) if e['sport'] == sport], key=sort_key):
        when = e.get('start') or e.get('date')
        rows.append(f"E {e['id']} | {when} | {e['home']} – {e['away']} | {e['comp']} | {e.get('why', '')}" + (' | tent' if e.get('tent') else '') + (f" | {e['note']}" if e.get('note') else ''))
    for s in sorted([s for s in data.get('series', []) if s['sport'] == sport], key=lambda s: s['from']):
        rows.append(f"S {s['id']} | {s['from']}–{s['to']} | {s['name']} | {s.get('tour', '')} | {s.get('place', '')}")
    return '\n'.join(rows) or 'keine Einträge'


# ---------- Änderungen einspielen ----------
def check_event(e):
    need = ['id', 'sport', 'comp', 'home', 'away', 'short']
    miss = [k for k in need if not e.get(k)]
    if miss:
        raise ValueError(f"Event {e.get('id')}: fehlt {miss}")
    if e['sport'] not in SPORTS:
        raise ValueError(f"Event {e['id']}: unbekannte Sportart {e['sport']}")
    if bool(e.get('start')) == bool(e.get('date')):
        raise ValueError(f"Event {e['id']}: genau eines von start oder date angeben")
    if e.get('start'):
        datetime.fromisoformat(e['start'].replace('Z', '+00:00'))
        if not e['start'].endswith('Z'):
            raise ValueError(f"Event {e['id']}: start muss UTC mit Z sein")
    else:
        datetime.strptime(e['date'], '%Y-%m-%d')


def check_series(s):
    for k in ['id', 'sport', 'name', 'from', 'to']:
        if not s.get(k):
            raise ValueError(f"Serie {s.get('id')}: fehlt {k}")
    datetime.strptime(s['from'], '%Y-%m-%d'); datetime.strptime(s['to'], '%Y-%m-%d')


def apply(data, patch):
    log = []
    evs = {e['id']: e for e in data.get('events', [])}
    for e in patch.get('upsert_events', []):
        check_event(e)
        log.append(('geändert ' if e['id'] in evs else 'neu ') + f"{e['id']} {e['home']} – {e['away']}")
        evs[e['id']] = e
    for i in patch.get('remove_events', []):
        if evs.pop(i, None):
            log.append(f'entfernt {i}')
    data['events'] = sorted(evs.values(), key=sort_key)
    ser = {s['id']: s for s in data.get('series', [])}
    for s in patch.get('upsert_series', []):
        check_series(s)
        log.append(('geändert ' if s['id'] in ser else 'neu ') + f"{s['id']} {s['name']}")
        ser[s['id']] = s
    for i in patch.get('remove_series', []):
        if ser.pop(i, None):
            log.append(f'entfernt {i}')
    data['series'] = sorted(ser.values(), key=lambda s: (s['from'], s['id']))
    if 'notes' in patch:
        data['notes'] = list(patch['notes']); log.append('Hinweise ersetzt')
    for pre, txt in patch.get('set_notes', {}).items():
        notes = [n for n in data.get('notes', []) if not n.startswith(pre)]
        if txt:
            notes.append(txt)
        data['notes'] = notes; log.append(f'Hinweis „{pre}“ aktualisiert')
    pk = next((f for f in data.get('fixtures', []) if f['key'] == 'pk'), None)
    if pk is not None and (patch.get('pk_round') or patch.get('pk_results')):
        teams = pk['teams']
        def idx(name):
            if name not in teams:
                teams.append(name)
            return teams.index(name)
        if patch.get('pk_round'):
            r = patch['pk_round']
            ms = [[m[0], idx(m[1]), idx(m[2]), m[3] if len(m) > 3 else '', m[4] if len(m) > 4 else 0] for m in r['m']]
            pk['rounds'] = [x for x in pk['rounds'] if x['n'] != r['n']] + [{'n': r['n'], 'm': ms}]
            pk['rounds'].sort(key=lambda x: x['n'])
            log.append(f"DFB-Pokal Runde {r['n']}: {len(ms)} Spiele")
        for h, a, sc in patch.get('pk_results', []):
            hit = False
            for r in pk['rounds']:
                for m in r['m']:
                    if teams[m[1]] == h and teams[m[2]] == a:
                        m[3] = sc; hit = True
            log.append(f"Pokal-Ergebnis {h} – {a} {sc}" + ('' if hit else ' (Spiel nicht gefunden)'))
    data['asOf'] = iso(now_utc())
    return log


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 1
    cmd = argv[1]
    html, data = load()
    if cmd == 'push':
        print(push_text(data) or 'NICHTS')
    elif cmd == 'status':
        print(status(data))
    elif cmd == 'show':
        print(show(data, argv[2]))
    elif cmd == 'apply':
        patch = json.loads(pathlib.Path(argv[2]).read_text(encoding='utf-8'))
        log = apply(data, patch)
        changed = save(data, html)
        print('\n'.join(log) or 'keine Änderungen'); print('Datei geändert' if changed else 'Datei unverändert')
    else:
        print(__doc__); return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
