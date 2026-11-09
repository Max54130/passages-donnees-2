"""Transforme les GTFS des réseaux en fichiers statiques par station.

Usage : python3 -I build.py RAW_DIR OUT_DIR [reseau ...]
Sortie par réseau (OUT_DIR/<reseau>/) :
  meta.json  : routes, calendrier (jours actifs par service), liste des stations
  s/<n>.json : départs théoriques de la station n
"""
import csv, io, json, os, sys, zipfile, datetime, collections

RAW, OUT = sys.argv[1], sys.argv[2]
NETS = json.load(open(os.environ.get('NETS_FILE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'networks.json')))
ONLY = sys.argv[3:] or list(NETS)
DAYS_BEFORE, DAYS_AFTER = 1, 35
TODAY = datetime.date.today()
BASE = TODAY - datetime.timedelta(days=DAYS_BEFORE)
NDAYS = DAYS_BEFORE + DAYS_AFTER


def rows(z, name):
    names = {n.split('/')[-1]: n for n in z.namelist()}
    if name not in names:
        return
    with z.open(names[name]) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig', errors='replace'))


def tsec(t):
    p = (t.strip() or '0:0:0').split(':')
    p = (p + ['0', '0'])[:3]
    return int(p[0]) * 3600 + int(p[1]) * 60 + int(float(p[2] or 0))


def h36(s):
    """Empreinte FNV-1a 32 bits en base 36 (identique côté fonction temps réel)."""
    h = 0x811c9dc5
    for b in s.encode('utf-8'):
        h ^= b
        h = (h * 0x01000193) & 0xffffffff
    a = '0123456789abcdefghijklmnopqrstuvwxyz'; o = ''
    while True:
        h, r = divmod(h, 36); o = a[r] + o
        if not h: return o


def ymd(s):
    return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def build(key):
    z = zipfile.ZipFile(os.path.join(RAW, key + '.zip'))
    out = os.path.join(OUT, key)
    os.makedirs(os.path.join(out, 's'), exist_ok=True)

    # Calendrier : bitmap des jours actifs sur la fenêtre
    cal = collections.defaultdict(lambda: [0] * NDAYS)
    wd = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    for r in rows(z, 'calendar.txt'):
        try:
            a, b = ymd(r['start_date']), ymd(r['end_date'])
        except (KeyError, ValueError, TypeError):
            continue
        bits = cal[r['service_id']]
        for i in range(NDAYS):
            d = BASE + datetime.timedelta(days=i)
            if a <= d <= b and r.get(wd[d.weekday()]) == '1':
                bits[i] = 1
    for r in rows(z, 'calendar_dates.txt'):
        try:
            i = (ymd(r['date']) - BASE).days
        except (KeyError, ValueError, TypeError):
            continue
        bits = cal[r['service_id']]
        if 0 <= i < NDAYS:
            bits[i] = 1 if r['exception_type'] == '1' else 0
    active = {s for s, b in cal.items() if any(b)}

    routes, rix = [], {}
    for r in rows(z, 'routes.txt'):
        rix[r['route_id']] = len(routes)
        routes.append([r.get('route_short_name') or r.get('route_long_name') or r['route_id'],
                       r.get('route_long_name', ''), (r.get('route_color') or '').strip() or '5d5d5d',
                       (r.get('route_text_color') or '').strip() or 'ffffff', int(r.get('route_type') or 3)])

    trips = {}
    for r in rows(z, 'trips.txt'):
        if r['service_id'] in active and r['route_id'] in rix:
            trips[r['trip_id']] = (rix[r['route_id']], r.get('trip_headsign', '').strip(), r['service_id'],
                                   r.get('direction_id', '') or '', (r.get('trip_short_name') or r.get('trip_headsign') or '').strip())

    stops = {}
    for r in rows(z, 'stops.txt'):
        stops[r['stop_id']] = (' '.join(r['stop_name'].split()),  # espaces en double retirés (Stan « Seichamps  Ecoquartier »)
                                r.get('parent_station', '').strip(),
                               r.get('location_type', '') or '0', r.get('stop_lat'), r.get('stop_lon'))

    board = bool(NETS[key].get('board'))
    gname = {}

    def group(sid):
        # Regroupement des quais : par station (parent_station), mais en gardant le NOM DU QUAI quand il
        # diffère du nom de la station. Les noms de station sont parfois périmés ou regroupent plusieurs
        # arrêts distincts (Stan : station « Gare de Nancy » = « Gare - Saint-Léon » + « Gare - Pierre Semard »,
        # « Saint-Georges » = « Deux Rives - O. de Gouges »). Gares SNCF (board) : regroupement par station inchangé.
        s = stops.get(sid)
        if not s:
            return sid
        p = s[1]
        if not (p and p in stops):
            return sid
        if board or s[0].strip().lower() == stops[p][0].strip().lower():
            return p
        k = p + '|' + s[0].strip().lower()
        if k not in gname:
            gname[k] = (s[0], '', '0', s[3], s[4])
        return k

    def info(g):
        return gname.get(g) or stops.get(g, (g, '', '0', 0, 0))

    # Arrêts de même nom à moins de 200 m regroupés (ex. Stan : quai d'arrivée et quai de départ du terminus
    # « Vandoeuvre Brabois - H. », rattachés à deux stations différentes). Gares SNCF : inchangé.
    canon = {}
    if not board:
        import math
        near = collections.defaultdict(list)
        for sid in sorted(stops):
            if (stops[sid][2] or '0') not in ('0', ''):
                continue
            g = group(sid)
            if g in canon:
                continue
            nm, _, _, la, lo = info(g)
            try:
                la, lo = float(la), float(lo)
            except (TypeError, ValueError):
                canon[g] = g
                continue
            k = nm.strip().lower()
            for (g2, la2, lo2) in near[k]:
                if math.hypot((la - la2) * 111000, (lo - lo2) * 111000 * math.cos(math.radians(la))) < 200:
                    canon[g] = g2
                    break
            else:
                canon[g] = g
                near[k].append((g, la, lo))
    _group = group

    def group(sid):
        g = _group(sid)
        return canon.get(g, g)

    # Passe 1 : dernier arrêt de chaque course (terminus)
    last, first = {}, {}
    for r in rows(z, 'stop_times.txt'):
        t = r['trip_id']
        if t in trips:
            q = int(float(r['stop_sequence'] or 0))
            if t not in last or q > last[t][0]:
                last[t] = (q, r['stop_id'])
            if t not in first or q < first[t][0]:
                first[t] = (q, r['stop_id'])
    has_rt = bool(NETS[key].get('rt'))

    # Passe 2 : départs par station
    svc_ix, head_ix, trip_ix = {}, {}, {}
    svcs, heads = [], []
    per = collections.defaultdict(list)
    tseq = collections.defaultdict(list)
    for r in rows(z, 'stop_times.txt'):
        t = r['trip_id']
        if t not in trips:
            continue
        q = int(float(r['stop_sequence'] or 0))
        is_last = last[t][0] == q
        no_pick = r.get('pickup_type', '0') == '1'
        if (is_last or no_pick) and not board:
            continue
        dep = r.get('departure_time') or r.get('arrival_time')
        arr = r.get('arrival_time') or dep
        if not dep:
            continue
        ri, hs, sv, di, num = trips[t]
        if NETS[key].get('head') == 'terminus' or not hs:
            hs = stops.get(last[t][1], ('',))[0]
        if sv not in svc_ix:
            svc_ix[sv] = len(svcs); svcs.append(''.join(map(str, cal[sv])))
        for name in (hs,) + ((stops.get(first[t][1], ('',))[0],) if board else ()):
            if name not in head_ix:
                head_ix[name] = len(heads); heads.append(name)
        if not is_last:
            tseq[t].append((q, group(r['stop_id'])))
        row = (ri, head_ix[hs], svc_ix[sv], tsec(dep), t, q, r['stop_id'], di)
        if board:
            kind = 2 if is_last else (1 if first[t][0] == q else (3 if no_pick else 0))
            row += (tsec(arr), head_ix[stops.get(first[t][1], ('',))[0]], kind, num)
        per[group(r['stop_id'])].append(row)

    order = sorted(per.items(), key=lambda x: info(x[0])[0])
    gix0 = {g: i for i, (g, _) in enumerate(order)}
    tfull = {}
    if board:  # gares desservies avant / après, pour l'affichage « via »
        for t, lst in tseq.items():
            seq = sorted(lst) + [(last[t][0], group(last[t][1]))]
            tfull[t] = ([q for q, _ in seq], [gix0.get(g, -1) for _, g in seq])
    stations = []
    for i, (g, lst) in enumerate(order):
        if board:
            import bisect
            for k, x in enumerate(lst):
                qs, gs = tfull.get(x[4], ([], []))
                j = bisect.bisect_left(qs, x[5])
                nxt = [v for v in gs[j + 1:-1] if v >= 0][:4]
                prv = [v for v in gs[max(1, j - 3):j] if v >= 0]
                lst[k] = x + (nxt, prv)
        name, _, _, lat, lon = info(g)
        lst.sort(key=lambda x: x[3])
        sids = sorted({x[6] for x in lst}); six = {s: j for j, s in enumerate(sids)}
        rset = sorted({x[0] for x in lst}, key=lambda k: routes[k][0])
        data = {'stops': sids,
                'd': ([[x[0], x[1], x[2], x[3], h36(x[4]), x[5], six[x[6]], x[7]] + list(x[8:]) for x in lst] if (has_rt or board)
                      else [[x[0], x[1], x[2], x[3]] for x in lst])}
        if not (has_rt or board):
            data['stops'] = []
        with open(os.path.join(out, 's', f'{i}.json'), 'w') as f:
            json.dump(data, f, separators=(',', ':'), ensure_ascii=False)
        try:
            ll = [round(float(lat), 5), round(float(lon), 5)]
        except (TypeError, ValueError):
            ll = [0, 0]
        stations.append([name, ll[0], ll[1], rset])

    gix = {g: i for i, (g, _) in enumerate(sorted(per.items(), key=lambda x: info(x[0])[0]))}
    pc = collections.defaultdict(collections.Counter)
    for t, lst in tseq.items():
        lst.sort()
        seqg = [gix[g] for _, g in lst]
        lg = group(last[t][1])
        seqg.append(gix.get(lg, -1))
        dd = [x for i, x in enumerate(seqg) if i == 0 or x != seqg[i - 1]]
        ri, hs = trips[t][0], trips[t][1]
        if NETS[key].get('head') == 'terminus' or not hs:
            hs = stops.get(last[t][1], ('',))[0]
        if hs in head_ix:
            pc[(ri, head_ix[hs])][tuple(dd)] += 1
    pats = []
    for (ri, hi), cnt in pc.items():
        pat, n = cnt.most_common(1)[0]
        pats.append([ri, hi, list(pat), sum(cnt.values())])
    meta = {'key': key, 'name': NETS[key]['name'], 'city': NETS[key]['city'], 'src': NETS[key]['src'],
            'built': datetime.datetime.now().isoformat(timespec='minutes'), 'base': BASE.isoformat(),
            'routes': routes, 'svc': svcs, 'heads': heads, 'stations': stations,
            'rt': bool(NETS[key].get('rt')), 'pat': pats, 'board': board}
    with open(os.path.join(out, 'meta.json'), 'w') as f:
        json.dump(meta, f, separators=(',', ':'), ensure_ascii=False)
    n = sum(len(v) for v in per.values())
    print(f'{key}: {len(stations)} stations, {len(routes)} lignes, {n} départs, {len(trips)} courses', flush=True)
    return set(trips)


if __name__ == '__main__':
    for k in ONLY:
        try:
            build(k)
        except Exception as e:  # un réseau défaillant ne bloque pas les autres
            print(f'{k}: ECHEC {e!r}', flush=True)
