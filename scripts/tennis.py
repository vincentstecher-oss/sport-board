#!/usr/bin/env python3
"""Tennis-Matches automatisch eintragen, ohne Claude.

Quelle: ESPN (site.api.espn.com, ohne Schlüssel), ATP-Tour-Scoreboard.

Regeln (Vincent):
  - alle Spiele von Alexander Zverev ab dem Achtelfinale, egal bei welchem Turnier (why "Zverev")
  - Duelle zweier Spieler aus den Top 10 der Weltrangliste (why "Top-10-Duell")
Gruppenspiele (z. B. ATP Finals) zählen wie K.o.-Runden. Frühe Runden (Qualifikation, 1. bis 3. Runde, Round of 32/64/128)
zählen für Zverev nicht; ein Duell zweier Top-10-Spieler zählt in jeder Runde.

Termine heißen tn-<ESPN-ID>; nur diese verwaltet das Skript. Der Davis Cup steht nicht im ATP-Feed und bleibt Handarbeit.
Das Skript wirft nie eine Ausnahme nach außen: Probleme landen als Warnung in WARN_FILE (die Action meldet sie), damit
die übrigen Skripte der Action weiterlaufen.

Aufruf: python3 scripts/tennis.py [--dry-run]
"""
import json, os, re, sys, time, pathlib, urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import board  # noqa: E402

SCORE = 'https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard'
RANKINGS = ['https://site.api.espn.com/apis/site/v2/sports/tennis/atp/rankings',
            'https://site.web.api.espn.com/apis/v2/sports/tennis/atp/rankings',
            'https://site.api.espn.com/apis/v2/sports/tennis/atp/rankings']
ZVEREV = 'alexander zverev'
EARLY = re.compile(r'qualif|round of (32|64|128)|1st round|2nd round|3rd round|round [123]\b|first round|second round|third round')
LATE = re.compile(r'round of 16|quarter|semi|final|round robin|group')
BACK, AHEAD = 3, 10  # Tage zurück (Ergebnisse) und voraus (Ansetzungen)


def fetch(url):
    err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (sport-board, github actions)', 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f'{url}: {err}')


def utc(s):
    s = s.replace('Z', '+00:00')
    if len(s) == 22:
        s = s[:16] + ':00' + s[16:]
    return datetime.fromisoformat(s)


def norm(n):
    return re.sub(r'\s+', ' ', (n or '').strip().lower())


def top10():
    """Namen der Top 10 der Weltrangliste (klein geschrieben) oder None, wenn nicht abrufbar."""
    for url in RANKINGS:
        try:
            d = fetch(url)
        except Exception:  # noqa: BLE001
            continue
        found = []

        def walk(x):
            if isinstance(x, dict):
                a = x.get('athlete')
                cur = x.get('current')
                if isinstance(a, dict) and isinstance(cur, (int, float)) and a.get('displayName'):
                    found.append((int(cur), norm(a['displayName'])))
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(d)
        names = [n for r, n in sorted(set(found)) if r <= 10]
        if len(names) >= 8:
            return set(names)
    return None


def players(c):
    out = []
    for x in sorted(c.get('competitors') or [], key=lambda x: x.get('order', 0)):
        a = x.get('athlete') or {}
        out.append((a.get('displayName') or a.get('fullName') or '', (a.get('shortName') or '').strip(), x))
    return out if len(out) == 2 else None


def last(name):
    p = name.split()
    return (' '.join(p[1:]) if len(p) > 1 else name).upper()


def round_text(c):
    bits = [json.dumps(c.get(k), ensure_ascii=False) for k in ('round', 'type', 'notes', 'headline', 'description') if c.get(k)]
    return norm(' '.join(bits))


def score_text(winner, loser):
    ws, ls = winner.get('linescores') or [], loser.get('linescores') or []
    sets = []
    for a, b in zip(ws, ls):
        va, vb = a.get('value'), b.get('value')
        if va is None or vb is None:
            continue
        s = f'{int(va)}-{int(vb)}'
        tb = a.get('tiebreak') if int(va) < int(vb) else b.get('tiebreak')
        if tb is not None and {int(va), int(vb)} == {6, 7}:
            s += f'({int(tb)})'
        sets.append(s)
    return ', '.join(sets)


def parse(tour, c, t10):
    """ESPN-Match -> (Termin, Ergebnis) oder None."""
    ps = players(c)
    if not ps or not c.get('date') or not c.get('id'):
        return None
    (n1, _, x1), (n2, _, x2) = ps
    if not n1 or not n2 or 'tbd' in norm(n1 + n2) or 'bye' in norm(n1 + n2):
        return None
    zv = ZVEREV in (norm(n1), norm(n2))
    duel = t10 is not None and norm(n1) in t10 and norm(n2) in t10
    rt = round_text(c)
    late = bool(LATE.search(rt)) or not rt
    if EARLY.search(rt) and not LATE.search(rt):
        late = False
    why = None
    if zv and late:
        why = 'Zverev'
    elif duel:
        why = 'Top-10-Duell'
    if not why:
        return None
    ev = {'id': f"tn-{c['id']}", 'sport': 'tennis', 'comp': tour['name'], 'home': n1, 'away': n2,
          'short': f'{last(n1)}–{last(n2)}', 'why': why, 'dur': 150, 'start': board.iso(utc(c['date']))}
    if zv and duel:
        ev['why'] = 'Zverev, Top-10-Duell'
    place = ((tour.get('venue') or {}).get('displayName')) or ''
    if place:
        ev['place'] = place
    st = ((c.get('status') or {}).get('type') or {})
    res = None
    if st.get('completed') or st.get('name') == 'STATUS_FINAL':
        w = next((x for x in (x1, x2) if x.get('winner')), None)
        if w is not None:
            lo = x2 if w is x1 else x1
            wn = n1 if w is x1 else n2
            sc = score_text(w, lo)
            res = f'{last(wn).title()} siegt' + (f' {sc}' if sc else '')
    return ev, res


def main(dry=False):
    warnings, log = [], []
    try:
        html, data = board.load(board.INDEX)
        now = board.now_utc()
        today = board.today_berlin()
        d0, d1 = today - timedelta(days=BACK), today + timedelta(days=AHEAD)
        t10 = top10()
        if t10 is None:
            warnings.append('Tennis: Weltrangliste nicht abrufbar, nur Zverev-Spiele werden eingetragen (scripts/tennis.py, RANKINGS prüfen)')
        d = fetch(f"{SCORE}?dates={d0.strftime('%Y%m%d')}-{d1.strftime('%Y%m%d')}&limit=200")
        found, seen_matches = {}, 0
        for tour in d.get('events', []):
            for g in tour.get('groupings') or [{'competitions': tour.get('competitions') or []}]:
                gname = norm(((g.get('grouping') or {}).get('displayName')) or (g.get('displayName')) or "men's singles")
                if 'single' not in gname or 'women' in gname or 'double' in gname:
                    continue
                for c in g.get('competitions') or []:
                    seen_matches += 1
                    p = parse(tour, c, t10)
                    if p:
                        found[p[0]['id']] = p
        if d.get('events') and not seen_matches:
            warnings.append('Tennis: Turniere gefunden, aber keine Einzel-Matches lesbar (ESPN-Aufbau geändert? scripts/tennis.py prüfen)')

        evs = data.get('events', [])
        before = json.dumps(sorted(evs, key=board.sort_key), ensure_ascii=False, sort_keys=True)
        out = []
        for e in evs:
            if not e['id'].startswith('tn-'):
                out.append(e); continue
            if e['id'] in found:
                new, res = found.pop(e['id'])
                keep = {k: e[k] for k in ('note',) if k in e}
                if res:
                    new['result'] = res
                elif e.get('result'):
                    new['result'] = e['result']
                if new['start'] != e.get('start'):
                    log.append(f"Ansetzung geändert: {new['home']} – {new['away']} {new['start']}")
                out.append({**new, **keep}); continue
            started = e.get('start') and board.ev_dt(e) <= now.astimezone(board.BERLIN)
            if not started and d0 <= board.ev_day(e) <= d1 and seen_matches:
                log.append(f"entfernt (nicht mehr im Spielplan): {e['home']} – {e['away']}"); continue
            out.append(e)
        for i, (e, res) in found.items():
            if i not in {x['id'] for x in evs}:
                if res:
                    e['result'] = res
                if board.ev_day(e) >= d0:
                    log.append(f"neu: {e['comp']} {e['home']} – {e['away']} ({e['start']})"); out.append(e)
        data['events'] = sorted(out, key=board.sort_key)
        changed = json.dumps(data['events'], ensure_ascii=False, sort_keys=True) != before
        if changed:
            data['asOf'] = board.iso(now)
        print('Tennis: ' + ('; '.join(log) or 'keine Änderungen'))
        if not dry:
            print('Datei geändert' if changed and board.save(data, html, board.INDEX) else 'Datei unverändert')
    except Exception as ex:  # noqa: BLE001
        warnings.append(f'Tennis: Lauf fehlgeschlagen ({type(ex).__name__}: {ex})')
    if os.environ.get('WARN_FILE'):
        with open(os.environ['WARN_FILE'], 'a', encoding='utf-8') as fh:
            fh.write(''.join(w + '\n' for w in warnings))
    if warnings:
        print('WARNUNGEN:\n' + '\n'.join(warnings))
    return 0


if __name__ == '__main__':
    sys.exit(main('--dry-run' in sys.argv))
