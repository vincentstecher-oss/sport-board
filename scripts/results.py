#!/usr/bin/env python3
"""Ergebnisse automatisch eintragen, ohne Claude.

Trägt in den Datenblock von index.html nur abgeschlossene Ergebnisse ein und überschreibt nie vorhandene:
  - Formel 1 (Rennen, Qualifying, Sprint) aus der Jolpica-API (api.jolpi.ca, Ergast-kompatibel)
      Rennen/Sprint: "1. Antonelli, 2. Leclerc, 3. Verstappen"   Qualifying: "Pole: Verstappen, 2. Norris, 3. Leclerc"
  - DFB-Pokal aus OpenLigaDB (api.openligadb.de): Stand nach 120 Minuten "2-1", nach Elfmeterschießen "1-1, 4-3 i.E.",
      in den Pokal-Spielplan (fixtures pk) und in die Pokal-Termine
  - Fußball-Termine (events mit sport fussball): Ergebnis aus dem passenden Spiel im Spielplan übernehmen,
      sobald der Termin vorbei ist und der Spielplan ein Ergebnis hat

Aufruf: python3 scripts/results.py [--dry-run] [--file PFAD]
Bei Unklarheit (kein eindeutiger Treffer, unbekannte Teamnamen, Quelle nicht erreichbar) wird nichts eingetragen;
Hinweise dazu landen als Warnung in der Datei aus WARN_FILE.
"""
import json, os, sys, time, pathlib, urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import board  # noqa: E402

JOLPICA = 'https://api.jolpi.ca/ergast/f1/{}.json?limit=100'
OLDB = 'https://api.openligadb.de/getmatchdata/dfb/{}'
F1_PATH = {'Rennen': 'results', 'Sprint': 'sprint', 'Qualifying': 'qualifying'}
F1_KEY = {'Rennen': 'Results', 'Sprint': 'SprintResults', 'Qualifying': 'QualifyingResults'}
F1_SCHED = {'Sprint': 'Sprint', 'Qualifying': 'Qualifying'}  # Rennen: date/time des Rennens selbst
# OpenLigaDB-Namen -> Namen im Board (alles andere wird unverändert verglichen)
OLDB_NAMES = {
    'Bayer 04 Leverkusen': 'Bayer Leverkusen', '1. FC Union Berlin': 'Union Berlin', '1. FSV Mainz 05': 'FSV Mainz 05',
    'SV Werder Bremen': 'Werder Bremen', 'SV 07 Elversberg': 'SV Elversberg', '1. FC Magdeburg': 'FC Magdeburg',
    'DSC Arminia Bielefeld': 'Arminia Bielefeld', '1. FC Heidenheim 1846': '1. FC Heidenheim', 'Sport-Club Freiburg': 'SC Freiburg',
    'TSG 1899 Hoffenheim': 'TSG Hoffenheim', 'Bayern München': 'FC Bayern München', 'VfB 1921 Krieschow': 'VfB Krieschow',
}


def fetch(url):
    err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'sport-board/1.0 (+github actions)', 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(4 * (attempt + 1))
    raise RuntimeError(f'{url}: {err}')


def utc(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))


def ev_end(e):
    """Ende eines Termins (UTC) oder None, wenn keine Uhrzeit bekannt ist."""
    if not e.get('start'):
        return None
    return utc(e['start']) + timedelta(minutes=e.get('dur') or 120)


# ---------- Formel 1 ----------
def session_dt(race, typ):
    s = race if typ == 'Rennen' else race.get(F1_SCHED[typ])
    if not s or not s.get('date'):
        return None
    return utc(f"{s['date']}T{(s.get('time') or '00:00:00Z')}")


def f1_text(typ, rows):
    by = {}
    for r in rows:
        try:
            by[int(r['position'])] = r['Driver']['familyName']
        except (KeyError, ValueError, TypeError):
            continue
    if not all(p in by for p in (1, 2, 3)):
        return None
    first = f'Pole: {by[1]}' if typ == 'Qualifying' else f'1. {by[1]}'
    return f'{first}, 2. {by[2]}, 3. {by[3]}'


def f1(data, now, warnings, log, cache):
    todo = [e for e in data.get('events', []) if e['sport'] == 'f1' and not e.get('result') and e.get('away') in F1_PATH]
    todo = [e for e in todo if (ev_end(e) or datetime.combine(board.ev_day(e) + timedelta(days=1), datetime.min.time(), timezone.utc)) <= now]
    out = {}
    for e in todo:
        year = board.ev_day(e).year
        if year not in cache:
            try:
                cache[year] = fetch(JOLPICA.format(year))['MRData']['RaceTable']['Races']
            except Exception as ex:  # noqa: BLE001
                warnings.append(f'F1: Kalender {year} nicht erreichbar ({ex})'); cache[year] = None
        races = cache[year]
        if not races:
            continue
        typ = e['away']
        hits = []
        for race in races:
            dt = session_dt(race, typ)
            if not dt:
                continue
            if e.get('start'):
                ok = abs(dt - utc(e['start'])) <= timedelta(hours=36)
            else:
                ok = abs((dt.date() - board.ev_day(e)).days) <= 1
            if ok:
                hits.append((race, dt))
        if len(hits) != 1:
            if not hits and typ != 'Sprint':
                warnings.append(f"F1: kein Jolpica-Termin für {e['id']} ({e['home']}, {typ})")
            continue
        race, dt = hits[0]
        if dt + timedelta(minutes=e.get('dur') or 120) > now:
            continue  # Session laut Jolpica noch nicht vorbei
        try:
            res = fetch(f"https://api.jolpi.ca/ergast/f1/{race['season']}/{race['round']}/{F1_PATH[typ]}.json?limit=100")
        except Exception as ex:  # noqa: BLE001
            warnings.append(f"F1: Ergebnis {e['id']} nicht erreichbar ({ex})"); continue
        rr = res['MRData']['RaceTable']['Races']
        if len(rr) != 1 or rr[0].get('round') != race['round']:
            continue  # noch kein Ergebnis veröffentlicht
        txt = f1_text(typ, rr[0].get(F1_KEY[typ], []))
        if txt:
            out[e['id']] = txt
    for i, txt in out.items():
        log.append(f'F1 {i}: {txt}')
    return out


# ---------- DFB-Pokal ----------
def oldb_score(m):
    """Stand nach 120 Minuten (bzw. 90 ohne Verlängerung) als 'H-G', mit Elfmeterschießen als 'H-G, x-y i.E.'"""
    if not m.get('matchIsFinished'):
        return None
    res = {r.get('resultTypeID'): (r.get('pointsTeam1'), r.get('pointsTeam2')) for r in m.get('matchResults') or []}
    base = res.get(4) or res.get(2)  # 4 = nach Verlängerung, 2 = Endergebnis
    if not base or None in base:
        return None
    sc = f'{base[0]}-{base[1]}'
    if 5 in res and None not in res[5]:  # Elfmeterschießen, OpenLigaDB zählt kumuliert
        p1, p2 = res[5][0] - base[0], res[5][1] - base[1]
        if base[0] != base[1] or p1 < 0 or p2 < 0 or p1 == p2:
            return None  # widersprüchlich, lieber nichts eintragen
        sc += f', {p1}-{p2} i.E.'
    elif base[0] == base[1]:
        return None  # Pokalspiel ohne Sieger: noch nicht fertig erfasst
    return sc


def pokal(data, now, warnings, log):
    pk = next((f for f in data.get('fixtures', []) if f['key'] == 'pk'), None)
    if not pk:
        return {}, {}
    today = now.astimezone(board.BERLIN).date()
    open_m = []
    for r in pk['rounds']:
        for m in r['m']:
            dt, day = ts_info(m[0])
            if not m[3] and day <= today and (dt is None or dt + timedelta(minutes=105) <= now):
                open_m.append(m)
    open_e = [e for e in data.get('events', []) if e['comp'] == 'DFB-Pokal' and not e.get('result')
              and (ev_end(e) or datetime.combine(board.ev_day(e), datetime.min.time(), timezone.utc)) <= now]
    if not open_m and not open_e:
        return {}, {}
    season = today.year if today.month >= 7 else today.year - 1
    try:
        feed = fetch(OLDB.format(season))
    except Exception as ex:  # noqa: BLE001
        warnings.append(f'DFB-Pokal: OpenLigaDB nicht erreichbar ({ex})'); return {}, {}
    teams = pk['teams']
    found = {}
    for m in feed:
        h = OLDB_NAMES.get(m['team1']['teamName'].strip(), m['team1']['teamName'].strip())
        a = OLDB_NAMES.get(m['team2']['teamName'].strip(), m['team2']['teamName'].strip())
        found.setdefault((h, a), []).append(m)
    fx_out, ev_out = {}, {}
    for m in open_m:
        h, a = teams[m[1]], teams[m[2]]
        cand = found.get((h, a), [])
        _, day = ts_info(m[0])
        cand = [x for x in cand if abs((utc(x['matchDateTimeUTC']).astimezone(board.BERLIN).date() - day).days) <= 3]
        if len(cand) != 1:
            if not cand:
                warnings.append(f'DFB-Pokal: {h} – {a} nicht in OpenLigaDB gefunden (Teamnamen in scripts/results.py prüfen)')
            continue
        sc = oldb_score(cand[0])
        if sc:
            fx_out[(m[1], m[2])] = sc
    for e in open_e:
        cand = [x for x in found.get((e['home'], e['away']), [])
                if abs((utc(x['matchDateTimeUTC']).astimezone(board.BERLIN).date() - board.ev_day(e)).days) <= 3]
        if len(cand) == 1:
            sc = oldb_score(cand[0])
            if sc:
                ev_out[e['id']] = sc
        elif not cand:
            warnings.append(f"DFB-Pokal: Termin {e['id']} {e['home']} – {e['away']} nicht in OpenLigaDB gefunden")
    for (hi, ai), sc in fx_out.items():
        log.append(f'Pokal-Spielplan: {teams[hi]} – {teams[ai]} {sc}')
    return fx_out, ev_out


def ts_info(ts):
    if len(ts) >= 10:
        dt = datetime.strptime(ts, '%y%m%d%H%M').replace(tzinfo=timezone.utc)
        return dt, dt.astimezone(board.BERLIN).date()
    return None, datetime.strptime(ts, '%y%m%d').date()


# ---------- Fußball-Termine aus den Spielplänen ----------
def football_events(data, now, log, extra_pk):
    fxs = {f['key']: f for f in data.get('fixtures', [])}
    out = {}
    for e in data.get('events', []):
        if e['sport'] != 'fussball' or e.get('result'):
            continue
        end = ev_end(e)
        if end is None or end > now:
            continue
        key = board.COMP_KEY.get(e['comp'])
        f = fxs.get(key)
        if not f:
            continue
        for r in f['rounds']:
            for m in r['m']:
                if f['teams'][m[1]] != e['home'] or f['teams'][m[2]] != e['away']:
                    continue
                sc = m[3] or (extra_pk.get((m[1], m[2])) if key == 'pk' else '')
                if sc and ts_info(m[0])[1] == board.ev_day(e):
                    out[e['id']] = sc
    for i, sc in out.items():
        log.append(f'Termin {i}: {sc}')
    return out


def main(argv):
    dry = '--dry-run' in argv
    path = pathlib.Path(argv[argv.index('--file') + 1]) if '--file' in argv else board.INDEX
    html, data = board.load(path)
    now = board.now_utc()
    warnings, log = [], []

    ev_res = f1(data, now, warnings, log, {})
    pk_fx, pk_ev = pokal(data, now, warnings, log)
    for i, sc in pk_ev.items():
        ev_res.setdefault(i, sc)
    for i, sc in football_events(data, now, log, pk_fx).items():
        ev_res.setdefault(i, sc)

    changed = False
    pk = next((f for f in data.get('fixtures', []) if f['key'] == 'pk'), None)
    if pk:
        for r in pk['rounds']:
            for m in r['m']:
                sc = pk_fx.get((m[1], m[2]))
                if sc and not m[3]:
                    m[3] = sc; changed = True
    for e in data.get('events', []):
        sc = ev_res.get(e['id'])
        if sc and not e.get('result'):
            e['result'] = sc; changed = True
    if changed:
        data['asOf'] = board.iso(now)
    if os.environ.get('WARN_FILE'):
        with open(os.environ['WARN_FILE'], 'a', encoding='utf-8') as fh:
            fh.write(''.join(w + '\n' for w in warnings))
    print('\n'.join(log) or 'Keine neuen Ergebnisse')
    if warnings:
        print('WARNUNGEN:\n' + '\n'.join(warnings))
    if not dry:
        print('Datei geändert' if changed and board.save(data, html, path) else 'Datei unverändert')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
