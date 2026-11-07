"""Écrit nets.json : réseaux construits avec ville, type de zone, emprise et options."""
import json, os, sys
NF, OUT = sys.argv[1], sys.argv[2]
n = json.load(open(NF)); res = []
for k, v in n.items():
    p = os.path.join(OUT, k, 'meta.json')
    if not os.path.exists(p):
        continue
    m = json.load(open(p))
    pts = [(s[1], s[2]) for s in m['stations'] if s[1] or s[2]]
    if not m['stations']:
        continue
    bb = [round(min(a for a, _ in pts), 3), round(min(b for _, b in pts), 3), round(max(a for a, _ in pts), 3), round(max(b for _, b in pts), 3)] if pts else None
    res.append({'key': k, 'name': v['name'], 'city': v['city'], 'area': (v.get('area') or [''])[0] if isinstance(v.get('area'), list) else v.get('area', ''),
                'rt': bool(m.get('rt')), 'board': bool(m.get('board')), 'bb': bb, 'alt': v.get('alt', [])})
json.dump(res, open(os.path.join(OUT, 'nets.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
# Index des noms d'arrêts pour la recherche dans l'appli : [nom, n° de réseau, n° de station, nb de lignes]
keys = [r['key'] for r in res]; rows = []
for ni, k in enumerate(keys):
    m = json.load(open(os.path.join(OUT, k, 'meta.json')))
    seen = {}
    for i, st in enumerate(m['stations']):
        nm = st[0]
        if nm in seen and len(m['stations'][seen[nm]][3]) >= len(st[3]):
            continue  # même nom dans le même réseau : on garde l'arrêt le plus desservi
        seen[nm] = i
    rows += [[nm, ni, i, len(m['stations'][i][3])] for nm, i in seen.items()]
rows.sort(key=lambda r: r[0])
json.dump({'n': keys, 's': rows}, open(os.path.join(OUT, 'stops.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
print(len(rows), 'arrêts dans stops.json')
print(len(res), 'réseaux dans nets.json')
