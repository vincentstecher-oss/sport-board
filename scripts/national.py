#!/usr/bin/env python3
"""Länderspiele automatisch eintragen, ohne Claude.

Quelle: ESPN-Spielpläne der Nationalteams (site.api.espn.com, ohne Schlüssel). Je Team ein Abruf über alle
Wettbewerbe (Nations League, EM- und WM-Qualifikation, EM, WM, Testspiele, Copa América).

Regeln (Vincent):
  - alle Spiele der deutschen Nationalmannschaft (why "DFB-Team", Markierung dfb)
  - Duelle zweier Top-Nationen untereinander (why "Topnationen-Duell"), Liste TOP unten

Ergebnisse (auch nach Verlängerung und Elfmeterschießen, z. B. "1-1, 4-3 i.E.") kommen aus dem ESPN-Spielbericht, sobald
das Spiel dort als beendet geführt wird. Termine heißen nt-<ESPN-ID>; nur diese verwaltet das Skript. Ist ein Team nicht abrufbar,
bleiben seine Termine unverändert.

Aufruf: python3 scripts/national.py [--dry-run]
"""
import json, os, sys, time, pathlib, urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import board  # noqa: E402

API = 'https://site.api.espn.com/apis/site/v2/sports/soccer'
GER = '481'
# Top-Nationen (ESPN-ID -> Name im Board). Duelle zweier Teams aus dieser Liste erscheinen im Board.
TOP = {'164': 'Spanien', '478': 'Frankreich', '448': 'England', '202': 'Argentinien', '205': 'Brasilien',
       '482': 'Portugal', '449': 'Niederlande', '459': 'Belgien', '162': 'Italien', '477': 'Kroatien'}
COMP = {'uefa.nations': 'Nations League', 'fifa.friendly': 'Testspiel', 'uefa.euroq': 'EM-Qualifikation', 'uefa.euro': 'EM',
        'fifa.world': 'WM', 'conmebol.america': 'Copa América', 'fifa.cwc': 'Klub-WM'}
DE = {  # ESPN-Name -> deutscher Name
    'Germany': 'Deutschland', 'Spain': 'Spanien', 'France': 'Frankreich', 'England': 'England', 'Argentina': 'Argentinien',
    'Brazil': 'Brasilien', 'Portugal': 'Portugal', 'Netherlands': 'Niederlande', 'Belgium': 'Belgien', 'Italy': 'Italien',
    'Croatia': 'Kroatien', 'Serbia': 'Serbien', 'Greece': 'Griechenland', 'Austria': 'Österreich', 'Switzerland': 'Schweiz',
    'Denmark': 'Dänemark', 'Norway': 'Norwegen', 'Sweden': 'Schweden', 'Poland': 'Polen', 'Czechia': 'Tschechien',
    'Czech Republic': 'Tschechien', 'Türkiye': 'Türkei', 'Turkey': 'Türkei', 'Wales': 'Wales', 'Scotland': 'Schottland',
    'Republic of Ireland': 'Irland', 'Northern Ireland': 'Nordirland', 'Hungary': 'Ungarn', 'Slovakia': 'Slowakei',
    'Slovenia': 'Slowenien', 'Ukraine': 'Ukraine', 'Romania': 'Rumänien', 'Bosnia-Herzegovina': 'Bosnien-Herzegowina',
    'Bosnia and Herzegovina': 'Bosnien-Herzegowina', 'Albania': 'Albanien', 'Georgia': 'Georgien', 'Iceland': 'Island',
    'Finland': 'Finnland', 'Israel': 'Israel', 'Luxembourg': 'Luxemburg', 'Kosovo': 'Kosovo', 'North Macedonia': 'Nordmazedonien',
    'Montenegro': 'Montenegro', 'Bulgaria': 'Bulgarien', 'Faroe Islands': 'Färöer', 'Liechtenstein': 'Liechtenstein',
    'Malta': 'Malta', 'Cyprus': 'Zypern', 'Armenia': 'Armenien', 'Azerbaijan': 'Aserbaidschan', 'Kazakhstan': 'Kasachstan',
    'Estonia': 'Estland', 'Latvia': 'Lettland', 'Lithuania': 'Litauen', 'Belarus': 'Belarus', 'Moldova': 'Moldau',
    'Andorra': 'Andorra', 'San Marino': 'San Marino', 'Gibraltar': 'Gibraltar', 'Uruguay': 'Uruguay', 'Colombia': 'Kolumbien',
    'Mexico': 'Mexiko', 'United States': 'USA', 'USA': 'USA', 'Canada': 'Kanada', 'Japan': 'Japan', 'South Korea': 'Südkorea',
    'Morocco': 'Marokko', 'Senegal': 'Senegal', 'Egypt': 'Ägypten', 'Nigeria': 'Nigeria', 'Ghana': 'Ghana',
    'Cameroon': 'Kamerun', 'Tunisia': 'Tunesien', 'Algeria': 'Algerien', 'Ivory Coast': 'Elfenbeinküste',
    "Côte d'Ivoire": 'Elfenbeinküste', 'Australia': 'Australien', 'Ecuador': 'Ecuador', 'Chile': 'Chile', 'Peru': 'Peru',
    'Paraguay': 'Paraguay', 'Bolivia': 'Bolivien', 'Venezuela': 'Venezuela', 'Qatar': 'Katar', 'Saudi Arabia': 'Saudi-Arabien',
    'Iran': 'Iran', 'Iraq': 'Irak', 'Curaçao': 'Curaçao', 'South Africa': 'Südafrika', 'New Zealand': 'Neuseeland',
}
CODE = {'Deutschland': 'GER', 'Niederlande': 'NED', 'Schweiz': 'SUI', 'Kroatien': 'CRO', 'Portugal': 'POR', 'Kosovo': 'KVX'}
CITY = {'Belgrade': 'Belgrad', 'Prague': 'Prag', 'Rome': 'Rom', 'Milano': 'Mailand', 'Milan': 'Mailand', 'Lisbon': 'Lissabon',
        'Brussels': 'Brüssel', 'Copenhagen': 'Kopenhagen', 'Cologne': 'Köln', 'Munich': 'München', 'Vienna': 'Wien',
        'Warsaw': 'Warschau', 'Athens': 'Athen', 'Naples': 'Neapel', 'Turin': 'Turin', 'Florence': 'Florenz', 'Seville': 'Sevilla',
        'Zurich': 'Zürich', 'Geneva': 'Genf', 'Moscow': 'Moskau', 'Bucharest': 'Bukarest', 'Luxembourg City': 'Luxemburg'}
DONE = {'STATUS_FULL_TIME', 'STATUS_FINAL', 'STATUS_FINAL_AET', 'STATUS_FINAL_PEN'}


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
    if len(s) == 22:  # 2026-11-13T19:45+00:00 ohne Sekunden
        s = s[:16] + ':00' + s[16:]
    return datetime.fromisoformat(s)


def num(v):
    """ESPN-Tore: mal Text ('2'), mal Objekt ({'value': 2.0, 'displayValue': '2'})."""
    if isinstance(v, dict):
        v = v.get('displayValue', v.get('value'))
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def shootout(x):
    v = x.get('shootoutScore')
    if v is None and isinstance(x.get('score'), dict):
        v = x['score'].get('shootoutScore')
    return num(v)


def de_name(team):
    n = team.get('displayName') or team.get('name') or '?'
    return DE.get(n, n)


def comp_of(e):
    lg = e.get('league') or {}
    slug = lg.get('slug') or ''
    if slug in COMP:
        return slug, COMP[slug]
    if slug.startswith('fifa.worldq'):
        return slug, 'WM-Qualifikation'
    return slug, lg.get('name') or lg.get('abbreviation') or 'Länderspiel'


def parse(e):
    """ESPN-Spiel -> (Termin, Status, Ergebnis) oder None."""
    c = (e.get('competitions') or [{}])[0]
    cs = c.get('competitors') or []
    home = next((x for x in cs if x.get('homeAway') == 'home'), None)
    away = next((x for x in cs if x.get('homeAway') == 'away'), None)
    if not home or not away or not e.get('date'):
        return None
    hid, aid = str(home['team'].get('id')), str(away['team'].get('id'))
    is_ger = GER in (hid, aid)
    if not is_ger and not (hid in TOP and aid in TOP):
        return None
    slug, comp = comp_of(e)
    h, a = de_name(home['team']), de_name(away['team'])
    code = lambda n, t: CODE.get(n) or (t.get('abbreviation') or n[:3]).upper()  # noqa: E731
    ev = {'id': f"nt-{e['id']}", 'sport': 'fussball', 'comp': comp, 'home': h, 'away': a,
          'short': f"{code(h, home['team'])}–{code(a, away['team'])}", 'why': 'DFB-Team' if is_ger else 'Topnationen-Duell',
          'dur': 115, 'start': board.iso(utc(e['date'])), 'src': slug}
    if is_ger:
        ev['dfb'] = True
    v = c.get('venue') or {}
    name, city = v.get('fullName') or '', ((v.get('address') or {}).get('city') or '').split(',')[0]
    city = CITY.get(city, city)
    name = name.replace('Olympic Stadium Berlin', 'Olympiastadion')
    place = f'{name}, {city}' if name and city and city not in name else (name or city)
    if place:
        ev['place'] = place
    st = ((e.get('status') or c.get('status') or {}).get('type') or {})
    res = None
    if st.get('name') in DONE or st.get('completed'):
        hs, as_ = num(home.get('score')), num(away.get('score'))
        if hs is not None and as_ is not None:
            res = f'{hs}-{as_}'
            hp, ap = shootout(home), shootout(away)
            if hp is not None and ap is not None and hs == as_ and hp != ap:
                res += f', {hp}-{ap} i.E.'
            elif st.get('name') == 'STATUS_FINAL_AET':
                res += ' n.V.'
    return ev, st.get('name') or '', res


def main(dry=False):
    path = board.INDEX
    html, data = board.load(path)
    now = board.now_utc()
    today = board.today_berlin()
    horizon = today + timedelta(days=370)
    warnings, log = [], []

    found, ok_teams = {}, set()
    for tid in [GER] + list(TOP):
        try:
            d = fetch(f'{API}/all/teams/{tid}/schedule?fixture=true')
        except Exception as ex:  # noqa: BLE001
            if tid == GER:
                warnings.append(f'Länderspiele: Spielplan Deutschland nicht erreichbar ({ex})')
            continue
        name = (d.get('team') or {}).get('displayName')
        want = 'Germany' if tid == GER else next(k for k, v in DE.items() if v == TOP[tid])
        if name != want:
            warnings.append(f'Länderspiele: ESPN-Team {tid} ist {name}, erwartet {want} (ID in scripts/national.py prüfen)'); continue
        ok_teams.add(tid)
        for e in d.get('events', []):
            p = parse(e)
            if p:
                found[p[0]['id']] = p

    evs = data.get('events', [])
    before = json.dumps(sorted(evs, key=board.sort_key), ensure_ascii=False, sort_keys=True)
    by_id = {e['id']: e for e in evs}
    out = []
    # 1) vorhandene Länderspiel-Termine: aktualisieren, Ergebnis nachtragen oder entfernen
    for e in evs:
        if not e['id'].startswith('nt-'):
            out.append(e); continue
        if e['id'] in found:
            new, _, _ = found.pop(e['id'])
            keep = {k: e[k] for k in ('result', 'note') if k in e}
            if new['start'] != e.get('start'):
                log.append(f"Anstoß geändert: {new['home']} – {new['away']} {new['start']}")
            out.append({**new, **keep}); continue
        started = e.get('start') and board.ev_dt(e) <= now.astimezone(board.BERLIN)
        if not started and board.ev_day(e) <= horizon and {GER} <= ok_teams and all(t in ok_teams for t in TOP):
            log.append(f"entfernt (nicht mehr im Spielplan): {e['home']} – {e['away']}"); continue
        out.append(e)
    # 2) neue Termine
    for i, (e, st, res) in found.items():
        if today <= board.ev_day(e) <= horizon and i not in by_id:
            log.append(f"neu: {e['comp']} {e['home']} – {e['away']} ({e['start']})"); out.append(e)
    # 3) Ergebnisse beendeter Spiele (der Spielplan mit fixture=true führt sie nicht mehr): Spielbericht abrufen
    for e in out:
        if not e['id'].startswith('nt-') or e.get('result') or not e.get('start'):
            continue
        t0 = utc(e['start'])
        if t0 + timedelta(minutes=105) > now or now - t0 > timedelta(days=3):
            continue
        slug = e.get('src') or 'uefa.nations'
        try:
            hd = fetch(f"{API}/{slug}/summary?event={e['id'][3:]}").get('header') or {}
        except Exception as ex:  # noqa: BLE001
            warnings.append(f"Länderspiele: Ergebnis {e['home']} – {e['away']} nicht abrufbar ({ex})"); continue
        c = (hd.get('competitions') or [{}])[0]
        p = parse({'id': hd.get('id') or e['id'][3:], 'date': c.get('date') or e['start'], 'competitions': [c],
                   'status': c.get('status'), 'league': {'slug': slug}})
        if p and p[2]:
            e['result'] = p[2]; log.append(f"Ergebnis {e['home']} – {e['away']}: {p[2]}")

    data['events'] = sorted(out, key=board.sort_key)
    changed = json.dumps(data['events'], ensure_ascii=False, sort_keys=True) != before
    if changed:
        data['asOf'] = board.iso(now)
    if os.environ.get('WARN_FILE'):
        with open(os.environ['WARN_FILE'], 'a', encoding='utf-8') as fh:
            fh.write(''.join(w + '\n' for w in warnings))
    print('Länderspiele: ' + ('; '.join(log) or 'keine Änderungen') + f' (Teams abgerufen: {len(ok_teams)}/{1 + len(TOP)})')
    if warnings:
        print('WARNUNGEN:\n' + '\n'.join(warnings))
    if not dry:
        print('Datei geändert' if changed and board.save(data, html, path) else 'Datei unverändert')
    return 0


if __name__ == '__main__':
    sys.exit(main('--dry-run' in sys.argv))
