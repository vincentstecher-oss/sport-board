#!/usr/bin/env python3
"""Fußball automatisch aktualisieren, ohne Claude.

Lädt die Spielplan-Feeds von fixturedownload.com (Bundesliga, Premier League, La Liga, Serie A, Ligue 1,
Champions-League-Ligaphase) und aktualisiert im Datenblock von index.html:
  - fixtures: Anstoßzeiten und Ergebnisse aller Spieltage
  - tables: aus den Ergebnissen berechnet (Punkte, dann Tordifferenz, dann Tore)
  - events: Fußball-Termine nach Vincents Regeln (Bayern, Top-4-Duelle, Big Six, ...)
  - Bundesliga-Top-4 in Regeln, Hinweisen und DFB-Pokal-Markierungen
Der DFB-Pokal und K.-o.-Runden der Champions League stehen nicht im Feed; die pflegt der Claude-Lauf.

Aufruf: python3 scripts/football.py [--dry-run]
Unbekannte Teamnamen oder nicht erreichbare Feeds landen als Warnung in der Datei aus WARN_FILE; die betroffene Liga bleibt dann unverändert.
"""
import json, os, sys, time, pathlib, urllib.request
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import board  # noqa: E402

BERLIN = ZoneInfo('Europe/Berlin')
FEED = 'https://fixturedownload.com/feed/json/{}-2026'
LEAGUES = {  # key: (Feed, Wettbewerb im Board)
    'bl': ('bundesliga', 'Bundesliga'), 'pl': ('epl', 'Premier League'), 'll': ('la-liga', 'La Liga'),
    'sa': ('serie-a', 'Serie A'), 'l1': ('ligue-1', 'Ligue 1'), 'cl': ('champions-league', 'Champions League'),
}
NAMES = {
    'bl': {'Sport-Club Freiburg': 'SC Freiburg', '1. FC Union Berlin': 'Union Berlin', '1. FSV Mainz 05': 'FSV Mainz 05',
           'SV Werder Bremen': 'Werder Bremen', 'Bayer 04 Leverkusen': 'Bayer Leverkusen'},
    'pl': {'Arsenal': 'FC Arsenal', 'Hull': 'Hull City', 'Everton': 'FC Everton', 'Ipswich': 'Ipswich Town',
           "Nott'm Forest": 'Nottingham Forest', 'Brentford': 'FC Brentford', 'Brighton': 'Brighton & Hove Albion',
           'Man City': 'Manchester City', 'Newcastle': 'Newcastle United', 'Fulham': 'FC Fulham', 'Liverpool': 'FC Liverpool',
           'Bournemouth': 'AFC Bournemouth', 'Coventry': 'Coventry City', 'Spurs': 'Tottenham Hotspur', 'Chelsea': 'FC Chelsea',
           'Leeds': 'Leeds United', 'Sunderland': 'AFC Sunderland', 'Man Utd': 'Manchester United'},
    'll': {'Sevilla FC': 'FC Sevilla', 'R. Racing Club': 'Racing Santander', 'RCD Espanyol de Barcelona': 'Espanyol Barcelona',
           'RC Deportivo': 'Deportivo La Coruña', 'Atlético de Madrid': 'Atlético Madrid', 'Valencia CF': 'FC Valencia',
           'Celta': 'Celta Vigo', 'Athletic Club': 'Athletic Bilbao', 'Málaga CF': 'FC Málaga', 'Villarreal CF': 'FC Villarreal',
           'Getafe CF': 'FC Getafe'},
    'sa': {'Internazionale': 'Inter Mailand', 'Udinese': 'Udinese Calcio', 'Genoa': 'CFC Genua', 'Parma': 'Parma Calcio',
           'Frosinone': 'Frosinone Calcio', 'Venezia': 'FC Venedig', 'Atalanta': 'Atalanta Bergamo', 'Torino': 'FC Turin',
           'Milan': 'AC Mailand', 'Bologna': 'FC Bologna', 'Lazio': 'Lazio Rom', 'Roma': 'AS Rom', 'Fiorentina': 'AC Florenz',
           'Monza': 'AC Monza', 'Sassuolo': 'US Sassuolo', 'Napoli': 'SSC Neapel', 'Cagliari': 'Cagliari Calcio',
           'Como': 'Como 1907', 'Lecce': 'US Lecce'},
    'l1': {'Olympique de Marseille': 'Olympique Marseille', 'OGC Nice': 'OGC Nizza', 'Toulouse FC': 'FC Toulouse',
           'Estac Troyes': 'ESTAC Troyes', 'Havre Athletic Club': 'Le Havre AC', 'Stade Rennais FC': 'Stade Rennes',
           'RC Strasbourg Alsace': 'RC Straßburg', 'Stade Brestois 29': 'Stade Brest', 'Olympique Lyonnais': 'Olympique Lyon',
           'LOSC Lille': 'OSC Lille'},
    'cl': {'Club Brugge': 'Club Brügge', 'AEK Athens': 'AEK Athen', 'B. Dortmund': 'Borussia Dortmund', 'Porto': 'FC Porto',
           'Lille': 'OSC Lille', 'Barcelona': 'FC Barcelona', 'Stuttgart': 'VfB Stuttgart', 'Paris': 'Paris Saint-Germain',
           'Liverpool': 'FC Liverpool', 'Sporting CP': 'Sporting Lissabon', 'Napoli': 'SSC Neapel', 'PSV': 'PSV Eindhoven',
           'Bayern München': 'FC Bayern München', 'Man Utd': 'Manchester United', 'Slavia Praha': 'Slavia Prag', 'Como': 'Como 1907',
           'Lens': 'RC Lens', 'Sabah': 'Sabah Masazir', 'Inter': 'Inter Mailand', 'Arsenal': 'FC Arsenal', 'Atleti': 'Atlético Madrid',
           'Leipzig': 'RB Leipzig', 'Villarreal': 'FC Villarreal', 'Viking': 'Viking FK', 'Feyenoord': 'Feyenoord Rotterdam',
           'LASK': 'LASK Linz', 'Man City': 'Manchester City', 'Roma': 'AS Rom', 'Shakhtar': 'Schachtar Donezk',
           'S. Bratislava': 'Slovan Bratislava'},
}
BAYERN = 'FC Bayern München'
BIG6 = {'FC Arsenal', 'FC Chelsea', 'Manchester City', 'Manchester United', 'FC Liverpool', 'Tottenham Hotspur'}
LL3 = {'Real Madrid', 'FC Barcelona', 'Atlético Madrid'}
SA4 = {'Inter Mailand', 'AC Mailand', 'Juventus', 'SSC Neapel'}
L1 = {'Paris Saint-Germain', 'AS Monaco'}
WHY = {'bl': 'Top-4-Duell', 'pl': 'Big-Six-Duell', 'll': 'Top-3-Duell', 'sa': 'Gipfeltreffen', 'l1': 'PSG gegen Monaco', 'cl': 'Top-Duell'}
SKIP_WORDS = {'FC', 'AC', 'SC', 'SSC', 'AS', 'US', 'RC', 'CA', 'AFC', 'CFC', 'OGC', 'OSC', 'RB', 'SV', 'TSG', 'VfB', 'VfL', 'FSV', '1.', 'Real', 'Club', 'Stade', 'Olympique', 'Borussia', 'Bayer', 'Sporting'}


def fetch(slug):
    url = FEED.format(slug)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'sport-board/1.0 (+github actions)'})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f'{url}: {err}')


def ts_of(s):  # '2026-08-28 18:30:00Z' -> '2608281830' bzw. '260828' ohne Uhrzeit
    dt = datetime.strptime(s, '%Y-%m-%d %H:%M:%SZ')
    return dt.strftime('%y%m%d') if dt.strftime('%H:%M:%S') == '00:00:00' else dt.strftime('%y%m%d%H%M')


def ts_info(ts):
    if len(ts) >= 10:
        dt = datetime.strptime(ts, '%y%m%d%H%M').replace(tzinfo=timezone.utc)
        return dt, dt.astimezone(BERLIN).date()
    return None, datetime.strptime(ts, '%y%m%d').date()


def code(name, known):
    if name in known:
        return known[name]
    words = [w for w in name.replace('-', ' ').split() if w not in SKIP_WORDS and not w[:1].isdigit()] or name.split()
    return words[0][:3].upper()


def end_window(today):
    m = today.month + 3
    y = today.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    nxt = date(y + (m // 12), m % 12 + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


def table(fx, hl):
    st = {i: {'sp': 0, 'w': 0, 'd': 0, 'l': 0, 'p': 0, 'gf': 0, 'ga': 0} for i in range(len(fx['teams']))}
    for r in fx['rounds']:
        for m in r['m']:
            if not m[3]:
                continue
            a, b = (int(x) for x in m[3].split('-'))
            for t, f, g in ((m[1], a, b), (m[2], b, a)):
                s = st[t]; s['sp'] += 1; s['gf'] += f; s['ga'] += g
                if f > g: s['w'] += 1; s['p'] += 3
                elif f == g: s['d'] += 1; s['p'] += 1
                else: s['l'] += 1
    order = sorted(st, key=lambda i: (-st[i]['p'], -(st[i]['gf'] - st[i]['ga']), -st[i]['gf'], fx['teams'][i]))
    rows = []
    for rank, i in enumerate(order, 1):
        s, name = st[i], fx['teams'][i]
        row = {'r': rank, 't': name, 'sp': s['sp'], 'w': s['w'], 'd': s['d'], 'l': s['l'], 'p': s['p']}
        if hl(name, rank):
            row['hl'] = 1
        rows.append(row)
    return rows


def main(dry=False):
    path = board.INDEX
    html, data = board.load(path)
    before = json.dumps(data, ensure_ascii=False, sort_keys=True)
    today = board.today_berlin()
    warnings, log = [], []
    fixtures = {f['key']: f for f in data.get('fixtures', [])}

    # 1) Spielpläne und Ergebnisse
    for key, (slug, comp) in LEAGUES.items():
        fx = fixtures.get(key)
        if not fx:
            warnings.append(f'{key}: kein Spielplan im Board'); continue
        try:
            feed = fetch(slug)
        except Exception as e:  # noqa: BLE001
            warnings.append(f'{key}: Feed nicht erreichbar ({e})'); continue
        teams = fx['teams']
        names = NAMES.get(key, {})
        unknown = sorted({n for m in feed for n in (m['HomeTeam'], m['AwayTeam']) if names.get(n, n) not in teams})
        if unknown:
            warnings.append(f'{key}: unbekannte Teams im Feed: {", ".join(unknown)} (Zuordnung in scripts/football.py ergänzen)'); continue
        per = len(teams) // 2
        rounds = {}
        for m in feed:
            sc = '' if m.get('HomeTeamScore') is None or m.get('AwayTeamScore') is None else f"{m['HomeTeamScore']}-{m['AwayTeamScore']}"
            rounds.setdefault(m['RoundNumber'], []).append([ts_of(m['DateUtc']), teams.index(names.get(m['HomeTeam'], m['HomeTeam'])), teams.index(names.get(m['AwayTeam'], m['AwayTeam'])), sc, 0])
        old = {r['n']: r for r in fx['rounds']}
        changed = 0
        for n, ms in rounds.items():
            if len(ms) != per:
                continue  # unvollständige Runde: alten Stand behalten
            ms.sort(key=lambda x: (x[0], x[1]))
            o = old.get(n)
            if o is not None:
                ksc = {(x[1], x[2]): x[3] for x in o['m'] if x[3]}
                for x in ms:
                    if not x[3] and (x[1], x[2]) in ksc:
                        x[3] = ksc[(x[1], x[2])]
            if o is None or [x[:4] for x in sorted(o['m'], key=lambda x: (x[0], x[1]))] != [x[:4] for x in ms]:
                changed += 1
            old[n] = {'n': n, 'm': ms}
        fx['rounds'] = [old[n] for n in sorted(old)]
        if changed:
            log.append(f'{comp}: {changed} Spieltage aktualisiert')

    # 2) Tabellen und Bundesliga-Top-4
    tbl_old = {t['key']: t for t in data.get('tables', [])}
    bl = table(fixtures['bl'], lambda n, r: False)
    top4 = [r['t'] for r in bl[:4]]
    hl = {
        'bl': lambda n, r: r <= 4 or n == BAYERN, 'pl': lambda n, r: n in BIG6, 'll': lambda n, r: n in LL3,
        'sa': lambda n, r: n in SA4, 'l1': lambda n, r: n in L1, 'cl': lambda n, r: n == BAYERN,
    }
    data['tables'] = [{'key': k, 'name': tbl_old.get(k, {}).get('name', LEAGUES[k][1]), 'rows': table(fixtures[k], hl[k])} for k in LEAGUES if k in fixtures]

    # 3) Markierungen in den Spielplänen
    bl_teams = set(fixtures['bl']['teams'])
    top_set = {BAYERN} | set(top4) | BIG6 | LL3 | SA4 | L1
    def flag(key, h, a):
        if BAYERN in (h, a):
            return 1
        both = lambda s: h in s and a in s  # noqa: E731
        if key == 'bl': return 1 if both(set(top4)) else 0
        if key == 'pl': return 1 if both(BIG6) else 0
        if key == 'll': return 1 if both(LL3) else 0
        if key == 'sa': return 1 if both(SA4) else 0
        if key == 'l1': return 1 if both(L1) else 0
        if key == 'cl': return 1 if both(top_set) else 2 if (h in bl_teams or a in bl_teams) else 0
        return 0
    for key in LEAGUES:
        fx = fixtures.get(key)
        if not fx: continue
        for r in fx['rounds']:
            for m in r['m']:
                m[4] = flag(key, fx['teams'][m[1]], fx['teams'][m[2]])
    pk = fixtures.get('pk')
    if pk:
        for r in pk['rounds']:
            for m in r['m']:
                h, a = pk['teams'][m[1]], pk['teams'][m[2]]
                m[4] = 1 if BAYERN in (h, a) or h in top4 or a in top4 else 0

    # 4) Fußball-Termine nach den Regeln
    known = {}
    for e in data.get('events', []):
        p = str(e.get('short', '')).split('–')
        if e['sport'] == 'fussball' and len(p) == 2:
            known.setdefault(e['home'], p[0]); known.setdefault(e['away'], p[1])
    comps = {c: k for k, (_, c) in LEAGUES.items()}
    existing = {(e['comp'], e['home'], e['away']): e for e in data.get('events', []) if e['comp'] in comps}
    wanted, all_pairs, horizon = {}, set(), end_window(today)
    for key, (_, comp) in LEAGUES.items():
        fx = fixtures.get(key)
        if not fx: continue
        for r in fx['rounds']:
            for m in r['m']:
                h, a = fx['teams'][m[1]], fx['teams'][m[2]]
                all_pairs.add((comp, h, a))
                dt, day = ts_info(m[0])
                if not m[4] or not (today <= day <= horizon):
                    continue
                e = dict(existing.get((comp, h, a), {}))
                was_open = bool(e) and not e.get('start')
                e.update({'id': e.get('id') or f'{key}-{r["n"]}-{m[1]}-{m[2]}', 'sport': 'fussball', 'comp': comp, 'home': h, 'away': a,
                          'short': e.get('short') or f'{code(h, known)}–{code(a, known)}', 'dur': 115})
                if BAYERN in (h, a):
                    e['why'] = 'FC Bayern'; e['bayern'] = True
                else:
                    e['why'] = 'Deutsches Team' if m[4] == 2 else WHY[key]; e.pop('bayern', None)
                if dt:
                    e['start'] = board.iso(dt); e.pop('date', None)
                    if was_open:
                        e.pop('tent', None)
                        if e.get('note') == 'Anstoß noch nicht angesetzt': e.pop('note')
                else:
                    e['date'] = day.isoformat(); e.pop('start', None); e['tent'] = True
                    e.setdefault('note', 'Anstoß noch nicht angesetzt')
                if key == 'cl' and not e.get('note'):
                    e['note'] = f'Ligaphase, Spieltag {r["n"]}'
                wanted[(comp, h, a)] = e
    out = []
    for e in data.get('events', []):
        k = (e['comp'], e['home'], e['away'])
        if board.ev_day(e) < today:
            continue  # vorbei
        if k in wanted:
            out.append(wanted.pop(k))
        elif k in all_pairs and today <= board.ev_day(e) <= horizon:
            log.append(f'entfernt (Regel greift nicht mehr): {e["home"]} – {e["away"]}')
        else:
            if e['comp'] == 'DFB-Pokal' and not e.get('bayern'):
                e['why'] = 'Top-4-Team' if (e['home'] in top4 or e['away'] in top4) else 'DFB-Pokal'
            out.append(e)
    for e in wanted.values():
        log.append(f'neu: {e["comp"]} {e["home"]} – {e["away"]}'); out.append(e)
    data['events'] = sorted(out, key=board.sort_key)
    data['series'] = [s for s in data.get('series', []) if s['to'] >= today.isoformat()]

    # 5) Regeln und Hinweise zur Top 4
    t4 = ', '.join(top4)
    for r in data.get('rules', []):
        if r.get('t') == 'Bundesliga':
            r['d'] = f'Duelle der aktuellen Top 4: {t4}'
        if r.get('t') == 'DFB-Pokal':
            r['d'] = f'Alle Spiele des DFB-Pokals. Spiele des FC Bayern und der Bundesliga-Top-4 ({", ".join(t for t in top4 if t != BAYERN)}) sind hervorgehoben'
    notes = [n for n in data.get('notes', []) if not n.startswith('Die Bundesliga-Top-4') and not n.startswith('Tabellen:')]
    notes.append(f'Die Bundesliga-Top-4 gelten nach Tabelle vom {today.day}.{today.month}. ({t4}) und passen sich automatisch an.')
    notes.append('Tabellen: aus den Ergebnissen der Spielpläne berechnet, bei Punktgleichheit nach Tordifferenz und Toren.')
    data['notes'] = notes

    after = json.dumps(data, ensure_ascii=False, sort_keys=True)
    if after != before:
        stamp = board.iso(board.now_utc())
        data['fixturesAsOf'] = stamp; data['tablesAsOf'] = stamp; data['asOf'] = stamp
    if os.environ.get('WARN_FILE'):
        pathlib.Path(os.environ['WARN_FILE']).write_text('\n'.join(warnings) + ('\n' if warnings else ''), encoding='utf-8')
    print('\n'.join(log) or 'Keine inhaltlichen Änderungen')
    print('Top 4:', t4)
    if warnings:
        print('WARNUNGEN:\n' + '\n'.join(warnings))
    if not dry:
        print('Datei geändert' if board.save(data, html, path) else 'Datei unverändert')
    return 0


if __name__ == '__main__':
    sys.exit(main('--dry-run' in sys.argv))
