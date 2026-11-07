"""Construction des données sur Netlify (commande de build d'un serveur de stockage).

Télécharge les horaires officiels de chaque réseau listé dans build/networks.json,
les transforme en fichiers par station (build.py), puis écrit site/d/nets.json.
Un réseau en échec est ignoré : il n'apparaîtra simplement pas dans l'appli.
"""
import json, os, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
NF = os.path.join(HERE, 'networks.json')
RAW, OUT = '/tmp/raw', os.path.join(HERE, '..', 'site', 'd')
os.makedirs(RAW, exist_ok=True); os.makedirs(OUT, exist_ok=True)
nets = json.load(open(NF))
t0 = time.time(); ok = 0


def fetch(url, dst):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'prochains-passages-build'})
            with urllib.request.urlopen(req, timeout=180) as r, open(dst, 'wb') as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
            if os.path.getsize(dst) > 1000:
                return True
        except Exception as e:  # réseau instable : on réessaie
            print('  téléchargement', attempt + 1, e, flush=True)
            time.sleep(3)
    return False


for k, v in nets.items():
    if time.time() - t0 > float(os.environ.get('MAX_MIN', '13')) * 60:  # marge sous la durée maximale
        print('ARRET : temps de construction presque écoulé', flush=True)
        break
    zp = os.path.join(RAW, k + '.zip')
    if not fetch(v['gtfs'], zp):
        print(k, 'ECHEC téléchargement', flush=True)
        continue
    r = subprocess.run([sys.executable, '-I', os.path.join(HERE, 'build.py'), RAW, OUT, k],
                       capture_output=True, text=True, env={**os.environ, 'NETS_FILE': NF}, timeout=600)
    print(k, round(time.time() - t0), (r.stdout + r.stderr).strip()[-200:], flush=True)
    os.remove(zp)
    ok += 1

subprocess.run([sys.executable, '-I', os.path.join(HERE, 'make_nets.py'), NF, OUT], check=True)
print('terminé en', round(time.time() - t0), 's', flush=True)
