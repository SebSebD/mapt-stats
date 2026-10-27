#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stats-bunny.py : statistiques de fréquentation « maison » de La Machine à Prendre le Temps.

Ce script tourne SUR TON MAC (jamais sur le site). Il :
  1. récupère dans les journaux de Bunny les demandes de la petite image  _mapt/v.gif  envoyées par stats.js
     (une par page affichée, par vidéo lancée...) ;
  2. fait les totaux (par jour, par page, par vidéo, par pays...) et les garde dans un petit fichier local ;
  3. fabrique un rapport  rapport-stats.html  que tu ouvres sur ton Mac. Il n'est PAS publié : il est privé.

UTILISATION (Terminal, dans le dossier qui contient ce script)
    python3 stats-bunny.py --init       première fois : enregistre le numéro de ta zone Bunny et ta clé d'accès
    python3 stats-bunny.py              récupère les nouvelles données et ouvre le rapport
    python3 stats-bunny.py --sans-ouvrir    idem, sans ouvrir le rapport (pour une exécution automatique)
    python3 stats-bunny.py --rapport    refait seulement le rapport avec les données déjà enregistrées
    python3 stats-bunny.py --demo       montre un rapport d'EXEMPLE (données inventées) pour voir à quoi ça ressemble
    python3 stats-bunny.py --remise-a-zero    EFFACE tous les totaux (demande de taper REMISE A ZERO pour confirmer)

IMPORTANT : Bunny ne garde ses journaux que 3 JOURS. Lance le script au moins tous les 3 jours (idéalement
chaque jour), sinon les visites de la période manquante sont perdues.

UTILISATION SUR GITHUB (sans rien lancer sur ton Mac) : voir le dossier « depot-stats » et son LISEZMOI. Le script lit alors la clé,
le numéro de zone et le sel dans les « Secrets » GitHub (variables BUNNY_API_KEY, BUNNY_PULLZONE_ID, MAPT_STATS_SALT).

OÙ SONT LES FICHIERS : dans le dossier ~/MAPT-stats (modifiable avec la variable MAPT_STATS_DIR) :
    config.json (zone + clé : NE JAMAIS la mettre dans le dossier du site ni sur GitHub), stats.json (les totaux),
    rapport-stats.html (le rapport).

VIE PRIVÉE : les adresses IP arrivent déjà anonymisées par Bunny (dernier chiffre retiré, option par défaut : ne la
désactive pas). Le script ne garde AUCUNE adresse : seulement des totaux, plus (3 jours seulement) des empreintes
irréversibles servant à estimer le nombre de visiteurs différents par jour.

Ne nécessite aucun module à installer (Python 3.8 ou plus récent).
"""
import argparse
import datetime as dt
import getpass
import gzip
import hashlib
import json
import os
import random
import re
import secrets
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

# ----------------------------------------------------------------------------------------------------------------
# RÉGLAGES
# ----------------------------------------------------------------------------------------------------------------
DATA_DIR = Path(os.environ.get('MAPT_STATS_DIR', '~/MAPT-stats')).expanduser()
CONFIG_FILE = DATA_DIR / 'config.json'
STATE_FILE = DATA_DIR / 'stats.json'
REPORT_FILE = DATA_DIR / os.environ.get('MAPT_REPORT_NAME', 'rapport-stats.html')
API_URL = os.environ.get('BUNNY_LOGGING_URL', 'https://logging.bunnycdn.com').rstrip('/')
BEACON_PATH = '_mapt/v.gif'          # doit correspondre à BEACON dans stats.js
TIMEZONE = 'Europe/Paris'            # les jours sont comptés à l'heure de Paris
LOG_WINDOW_DAYS = 2.9                # Bunny garde les journaux 3 jours
RETENTION_DAYS = 790                 # on garde les totaux ~25 mois, pas plus
BOT_RE = re.compile(r'bot|crawl|spider|slurp|headless|lighthouse|pingdom|uptime|monitor|curl|wget|python|'
                    r'httpclient|okhttp|facebookexternalhit|preview', re.I)

# Noms lisibles dans le rapport (à compléter librement). Clé = adresse de la page, sans le « #/ ».
NOMS_PAGES = {
    'accueil': 'Accueil',
    'galeries': 'Galeries',
    'galeries/galerie-courtes-realisations': 'Galeries › Courtes réalisations',
    'galeries/galerie-par-thematiques': 'Galeries › Par thématiques',
    'galeries/galerie-premieres-machines': 'Galeries › Les 1ères machines',
    'galeries/galerie-ralentis': 'Galeries › Ralentis',
    'evenements': 'Évènements',
    'evenements/evenements-actualite': 'Évènements › Actualité',
    'evenements/evenements-passe': 'Évènements › Passés',
    'evenements/evenements-avenir': 'Évènements › À venir',
    'outils': 'Outils',
    'outils/outils-simulateur-acceleration': 'Outils › Simulateur d\'accélération',
    'outils/outils-preparation-tournage': 'Outils › Préparation tournage',
    'outils/outils-convertir-le-temps': 'Outils › Convertir le temps',
    'outils/outils-metronome': 'Outils › Métronome',
    'outils/outils-chronometre': 'Outils › Chrono & Timer',
    'dossiers': 'Dossiers',
    'contact': 'Contact',
    'mentions-legales': 'Mentions légales',
}
# Noms lisibles des vidéos (facultatif) : nom tel qu'il apparaît dans le rapport -> nom que tu préfères
NOMS_VIDEOS = {}
NOMS_PAYS = {
    'FR': 'France', 'BE': 'Belgique', 'CH': 'Suisse', 'LU': 'Luxembourg', 'CA': 'Canada', 'US': 'États-Unis',
    'DE': 'Allemagne', 'GB': 'Royaume-Uni', 'ES': 'Espagne', 'IT': 'Italie', 'NL': 'Pays-Bas', 'PT': 'Portugal',
    'IE': 'Irlande', 'AT': 'Autriche', 'DK': 'Danemark', 'SE': 'Suède', 'NO': 'Norvège', 'FI': 'Finlande',
    'PL': 'Pologne', 'MA': 'Maroc', 'DZ': 'Algérie', 'TN': 'Tunisie', 'SN': 'Sénégal', 'CI': 'Côte d\'Ivoire',
    'RE': 'La Réunion', 'MQ': 'Martinique', 'GP': 'Guadeloupe', 'NC': 'Nouvelle-Calédonie', 'PF': 'Polynésie française',
    'JP': 'Japon', 'CN': 'Chine', 'IN': 'Inde', 'BR': 'Brésil', 'AU': 'Australie', 'RU': 'Russie', 'UA': 'Ukraine',
}


# ----------------------------------------------------------------------------------------------------------------
# OUTILS
# ----------------------------------------------------------------------------------------------------------------
def load_config():
    """config.json (sur ton Mac) ou variables d'environnement BUNNY_API_KEY / BUNNY_PULLZONE_ID (sur GitHub, via les « Secrets »)."""
    cfg = load_json(CONFIG_FILE, None) or {}
    key = os.environ.get('BUNNY_API_KEY', '').strip()
    zone = os.environ.get('BUNNY_PULLZONE_ID', '').strip()
    if key:
        cfg['api_key'] = key
    if zone:
        cfg['pullzone_id'] = zone
    return cfg


def get_salt(state):
    """Le « sel » rend les empreintes de visiteurs irréversibles. Donné par MAPT_STATS_SALT (secret GitHub), il n'est
    JAMAIS écrit dans le fichier des totaux (utile quand ce fichier est public)."""
    env = os.environ.get('MAPT_STATS_SALT', '').strip()
    if env:
        state['salt'] = ''
        return env
    if not state.get('salt'):
        state['salt'] = secrets.token_hex(16)
    return state['salt']


def get_tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(TIMEZONE)
    except Exception:
        return dt.timezone.utc


def now_ms():
    return int(time.time() * 1000)


def iso_utc(ts_seconds):
    return dt.datetime.fromtimestamp(ts_seconds, dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_ts(value):
    """'2026-05-08T14:32:11.265Z' -> millisecondes depuis 1970 (ou None)."""
    try:
        m = re.match(r'(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d):(\d\d)(?:\.(\d+))?', str(value))
        if not m:
            return None
        y, mo, d, h, mi, s = [int(x) for x in m.groups()[:6]]
        frac = int((m.group(7) or '0')[:3].ljust(3, '0'))
        base = dt.datetime(y, mo, d, h, mi, s, tzinfo=dt.timezone.utc)
        return int(base.timestamp()) * 1000 + frac
    except Exception:
        return None


def load_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        print('Attention : le fichier %s est illisible (%s).' % (path, e))
        sys.exit(1)


def save_json(path, data, private=False):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    if private:
        os.chmod(tmp, 0o600)
    os.replace(tmp, str(path))


def new_state():
    return {'version': 1, 'salt': secrets.token_hex(16), 'last_ts': 0, 'seen': {}, 'days': {},
            'beacon_errors': 0, 'bots_ignored': 0, 'updated': None}


def clean_video_name(name):
    name = re.sub(r'[-_ ]*SiteWeb.*$', '', name, flags=re.I).strip()
    return NOMS_VIDEOS.get(name, name) or '(sans nom)'


def clean_label(value, limit=120):
    value = re.sub(r'[\x00-\x1f\x7f]', '', str(value or '')).strip()
    return value[:limit]


# ----------------------------------------------------------------------------------------------------------------
# ACCÈS AUX JOURNAUX BUNNY (API v2)
# ----------------------------------------------------------------------------------------------------------------
class BunnyError(Exception):
    pass


def api_get(url, key):
    req = urllib.request.Request(url, headers={'AccessKey': key, 'Accept': 'application/json',
                                               'Accept-Encoding': 'gzip', 'User-Agent': 'mapt-stats/1.0'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                if resp.headers.get('Content-Encoding') == 'gzip':
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode('utf-8'))
        except urllib.error.HTTPError as e:
            body = ''
            try:
                body = e.read().decode('utf-8', 'replace')
            except Exception:
                pass
            if e.code == 429 and attempt < 3:      # trop de demandes : on patiente (limite : 30 demandes / 10 s)
                time.sleep(11)
                continue
            code = ''
            try:
                code = json.loads(body).get('error', {}).get('code', '')
            except Exception:
                pass
            if e.code == 401:
                raise BunnyError('Bunny refuse l\'accès (401) : la clé d\'accès est absente ou fausse. Relance --init.')
            if e.code == 403:
                raise BunnyError('Bunny refuse l\'accès (403) : clé invalide, ou zone suspendue. Vérifie la clé (Bunny > Account settings > API Keys) et relance --init.')
            if e.code == 404 or code == 'logging_disabled':
                raise BunnyError('La journalisation n\'est pas activée (ou le numéro de zone est faux). Dans Bunny : ta zone (Pull Zone) > Logging : active-la, puis vérifie le numéro de zone avec --init.')
            raise BunnyError('Bunny a répondu avec l\'erreur %s. %s' % (e.code, body[:200]))
        except ssl.SSLCertVerificationError:
            raise BunnyError('Certificat de sécurité non reconnu par ce Python. Si tu as installé Python depuis python.org, lance '
                             '« Install Certificates.command » (dans le dossier Applications/Python 3.x), puis réessaie.')
        except urllib.error.URLError as e:
            if attempt < 3:
                time.sleep(3)
                continue
            raise BunnyError('Impossible de joindre Bunny (%s). Vérifie ta connexion internet.' % e.reason)
    raise BunnyError('Bunny ne répond pas.')


def fetch_beacon_logs(cfg, start_s, end_s):
    entries = []
    offset = 0
    while True:
        params = {'from': iso_utc(start_s), 'to': iso_utc(end_s), 'urlContains': BEACON_PATH,
                  'limit': 10000, 'offset': offset, 'order': 'asc'}
        url = '%s/v2/pullzones/%s/logs?%s' % (API_URL, cfg['pullzone_id'], urllib.parse.urlencode(params))
        data = api_get(url, cfg['api_key'])
        batch = data.get('data', [])
        entries.extend(batch)
        if not (data.get('pagination') or {}).get('hasMore') or not batch:
            break
        offset += len(batch)                       # on avance du nombre de lignes réellement reçues
    return entries


# ----------------------------------------------------------------------------------------------------------------
# TOTAUX
# ----------------------------------------------------------------------------------------------------------------
def empty_day():
    return {'visits': 0, 'views': 0, 'plays': 0, 'visitors': 0, 'vset': [],
            'pages': {}, 'videos': {}, 'actions': {}, 'countries': {}, 'refs': {}}


def bump(table, key, n=1):
    table[key] = table.get(key, 0) + n


def process_entries(state, entries, tz):
    """Ajoute les nouvelles demandes aux totaux. Retourne (comptées, robots, erreurs)."""
    counted = bots = errors = 0
    salt = get_salt(state)
    sets = {}                                       # jour -> ensemble des visiteurs (empreintes)
    for entry in sorted(entries, key=lambda e: e.get('timestamp', '')):
        rid = entry.get('requestId') or ''
        if rid and rid in state['seen']:
            continue                                # déjà compté lors d'un relevé précédent
        ts = parse_ts(entry.get('timestamp'))
        if ts is None:
            continue
        if rid:
            state['seen'][rid] = ts
        path = entry.get('path') or entry.get('url') or ''
        if BEACON_PATH not in path:
            continue
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        if 'e' not in q:
            continue                                # pas envoyée par stats.js (ex. adresse tapée à la main) : ignorée
        status = entry.get('statusCode') or 0
        if status >= 400:
            errors += 1                             # envoyée par stats.js mais refusée : 404 (fichier absent) ou 403 (site non autorisé)
            continue
        ua = entry.get('userAgent') or ''
        if not ua or BOT_RE.search(ua):
            bots += 1
            continue
        kind = (q.get('e') or [''])[0]
        name = clean_label((q.get('n') or [''])[0])
        if kind not in ('page', 'video', 'tool') or not name:
            continue

        day = dt.datetime.fromtimestamp(ts / 1000.0, tz).strftime('%Y-%m-%d')
        rec = state['days'].setdefault(day, empty_day())
        if day not in sets:
            sets[day] = set(rec.get('vset', []))
        vid = hashlib.sha256(('%s|%s|%s|%s' % (salt, entry.get('remoteIp') or '', ua, day)).encode('utf-8')).hexdigest()[:12]
        if vid not in sets[day]:
            sets[day].add(vid)
            rec['visitors'] += 1
            bump(rec['countries'], (entry.get('countryCode') or '??').upper())

        if kind == 'page':
            rec['views'] += 1
            bump(rec['pages'], name)
            if (q.get('s') or [''])[0] == '1':
                rec['visits'] += 1
                bump(rec['refs'], clean_label((q.get('ref') or [''])[0], 80) or '(accès direct)')
        elif kind == 'video':
            rec['plays'] += 1
            bump(rec['videos'], clean_video_name(name))
        else:
            bump(rec['actions'], name)
        counted += 1

    for day, s in sets.items():
        state['days'][day]['vset'] = sorted(s)
    return counted, bots, errors


def prune_state(state, tz):
    today = dt.datetime.now(tz).date()
    for day in list(state['days'].keys()):
        try:
            age = (today - dt.datetime.strptime(day, '%Y-%m-%d').date()).days
        except ValueError:
            continue
        if age > RETENTION_DAYS:
            del state['days'][day]
        elif age > 4:
            state['days'][day]['vset'] = []         # les empreintes ne servent plus : on les efface
    limit = now_ms() - int(3.3 * 24 * 3600 * 1000)
    state['seen'] = {k: v for k, v in state['seen'].items() if v >= limit}


def update_from_bunny(cfg, state, tz):
    now_s = time.time()
    earliest = now_s - LOG_WINDOW_DAYS * 24 * 3600
    last_s = state.get('last_ts', 0) / 1000.0
    if last_s and last_s < now_s - 3 * 24 * 3600:
        gap = (now_s - last_s) / 86400.0
        print('Attention : le dernier relevé date de %.1f jours. Bunny ne garde que 3 jours : les visites de la période '
              'manquante sont perdues. Lance le script plus souvent.' % gap)
    # on repart une heure AVANT le dernier relevé : des lignes de journal peuvent arriver en retard (les doublons sont écartés)
    start_s = max(earliest, (last_s - 3600) if last_s else earliest)
    entries = fetch_beacon_logs(cfg, start_s, now_s)
    counted, bots, errors = process_entries(state, entries, tz)
    state['bots_ignored'] = state.get('bots_ignored', 0) + bots
    state['beacon_errors'] = state.get('beacon_errors', 0) + errors
    state['last_ts'] = int(now_s * 1000)
    state['updated'] = dt.datetime.now(tz).strftime('%Y-%m-%d %H:%M')
    prune_state(state, tz)
    return len(entries), counted, bots, errors


# ----------------------------------------------------------------------------------------------------------------
# REMISE À ZÉRO
# ----------------------------------------------------------------------------------------------------------------
RESET_PHRASE = 'REMISE A ZERO'


def mark_existing_as_seen(cfg, state):
    """Relève les demandes déjà présentes dans les journaux de Bunny (3 jours) et les marque « déjà vues » SANS les
    compter : après la remise à zéro, seules les visites NOUVELLES seront comptées."""
    now_s = time.time()
    entries = fetch_beacon_logs(cfg, now_s - LOG_WINDOW_DAYS * 24 * 3600, now_s)
    n = 0
    for entry in entries:
        rid = entry.get('requestId') or ''
        ts = parse_ts(entry.get('timestamp'))
        if rid and ts is not None:
            state['seen'][rid] = ts
            n += 1
    return n


def cmd_reset(confirmation, tz):
    """Efface tous les totaux, après confirmation. `confirmation` : mot tapé (ou None : on le demande)."""
    if confirmation is None:
        print('ATTENTION : cette commande EFFACE définitivement tous les totaux (visites, pages, vidéos, pays...).')
        print('Seules les visites faites APRÈS la remise à zéro seront comptées.')
        try:
            confirmation = input('Pour confirmer, tape exactement  %s  (toute autre réponse annule) : ' % RESET_PHRASE)
        except EOFError:
            confirmation = ''
    if (confirmation or '').strip().upper() != RESET_PHRASE:
        print('Confirmation incorrecte : RIEN n\'a été effacé.')
        sys.exit(1)

    state = load_json(STATE_FILE, None) or new_state()
    cfg = load_config()
    marked = None
    if cfg.get('api_key') and cfg.get('pullzone_id'):
        try:
            marked = mark_existing_as_seen(cfg, state)
        except BunnyError as e:
            print('Attention : impossible de lire les journaux de Bunny (%s).' % e)
    else:
        print('Attention : clé ou numéro de zone Bunny absents.')
    if marked is None:
        print('Les visites des dernières heures encore présentes chez Bunny pourraient être recomptées au prochain relevé.')

    n_days = len(state.get('days', {}))
    state['days'] = {}
    state['bots_ignored'] = 0
    state['beacon_errors'] = 0
    state['last_ts'] = now_ms()
    state['updated'] = dt.datetime.now(tz).strftime('%Y-%m-%d %H:%M')
    state['reset_at'] = state['updated']
    prune_state(state, tz)
    save_json(STATE_FILE, state)
    build_report(state, REPORT_FILE)
    print('Remise à zéro effectuée : %d jour(s) de statistiques effacé(s)%s.' % (
        n_days, '' if marked is None else ', %d visite(s) déjà présente(s) chez Bunny ignorée(s)' % marked))
    print('Rapport : %s' % REPORT_FILE)


# ----------------------------------------------------------------------------------------------------------------
# RAPPORT
# ----------------------------------------------------------------------------------------------------------------
REPORT_TEMPLATE = r'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Statistiques — La Machine à Prendre le Temps</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 26px 18px 60px; background: #121212; color: #eee; font-family: Arial, sans-serif; line-height: 1.45; }
  main { max-width: 1080px; margin: 0 auto; }
  h1 { font-size: 24px; margin: 0 0 4px; }
  .sub { color: #9a9a9a; font-size: 14px; margin-bottom: 18px; }
  .bar { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 18px; }
  .bar button { background: #222; color: #ddd; border: 1px solid #444; border-radius: 999px; padding: 7px 16px; font-size: 14px; cursor: pointer; }
  .bar button.on { background: #fff; color: #111; border-color: #fff; font-weight: bold; }
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 16px; }
  .card { background: #1b1b1b; border: 1px solid #2e2e2e; border-radius: 12px; padding: 16px 18px; }
  .kpi .n { font-size: 32px; font-weight: bold; }
  .kpi .l { color: #aaa; font-size: 13px; }
  h2 { font-size: 15px; letter-spacing: .5px; text-transform: uppercase; color: #9fcdf7; margin: 0 0 12px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 12px; margin-top: 12px; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  td { padding: 6px 4px; border-top: 1px solid #2a2a2a; vertical-align: middle; }
  tr:first-child td { border-top: 0; }
  td.v { text-align: right; width: 64px; font-variant-numeric: tabular-nums; }
  td.b { width: 34%; }
  .b i { display: block; height: 8px; border-radius: 4px; background: #4ea1ef; }
  .empty { color: #777; font-size: 14px; }
  svg { width: 100%; height: auto; display: block; }
  .legend { display: flex; gap: 16px; font-size: 13px; color: #aaa; margin-top: 6px; }
  .legend span::before { content: ""; display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
  .legend .a::before { background: #4ea1ef; } .legend .c::before { background: #6fcf8d; }
  .note { color: #888; font-size: 13px; margin-top: 18px; }
  .reset { margin-top: 18px; text-align: right; }
  .reset button { background: transparent; color: #c98a8a; border: 1px solid #5a3a3a; border-radius: 8px; padding: 7px 14px; font-size: 13px; cursor: pointer; }
  .reset button:hover { background: #2a1717; color: #f0b0b0; }
  #dlg { position: fixed; inset: 0; background: rgba(0,0,0,.7); display: none; align-items: center; justify-content: center; padding: 18px; z-index: 10; }
  #dlg.open { display: flex; }
  #dlg .box { background: #1b1b1b; border: 1px solid #444; border-radius: 12px; max-width: 560px; padding: 22px 24px; }
  #dlg h2 { color: #f0b0b0; }
  #dlg ol { padding-left: 20px; margin: 10px 0; }
  #dlg code { background: #101010; border: 1px solid #333; border-radius: 5px; padding: 2px 6px; font-size: 13px; }
  #dlg .row { display: flex; gap: 10px; justify-content: flex-end; margin-top: 16px; flex-wrap: wrap; }
  #dlg .row a, #dlg .row button { background: #2a2a2a; color: #fff; border: 1px solid #555; border-radius: 8px; padding: 8px 14px; font-size: 14px; cursor: pointer; text-decoration: none; }
  #dlg .row a.go { background: #8a2f2f; border-color: #8a2f2f; font-weight: bold; }
  .warn { background: #3a2a10; border: 1px solid #7a5a20; color: #f3d9a4; border-radius: 10px; padding: 10px 14px; margin-bottom: 14px; font-size: 14px; }
</style>
</head>
<body>
<main>
  <h1>Statistiques de fréquentation</h1>
  <div class="sub">La Machine à Prendre le Temps · rapport privé · dernière mise à jour : <b id="upd"></b></div>
  <div id="warn"></div>
  <div class="bar" id="periods"></div>
  <div class="kpis" id="kpis"></div>
  <div class="card"><h2>Par jour</h2><div id="chart"></div>
    <div class="legend"><span class="a">Pages vues</span><span class="c">Visiteurs différents</span></div></div>
  <div class="grid">
    <div class="card"><h2>Pages les plus vues</h2><div id="t-pages"></div></div>
    <div class="card"><h2>Vidéos lancées</h2><div id="t-videos"></div></div>
    <div class="card"><h2>Provenance des visites</h2><div id="t-refs"></div></div>
    <div class="card"><h2>Pays des visiteurs</h2><div id="t-countries"></div></div>
    <div class="card"><h2>Autres actions</h2><div id="t-actions"></div></div>
  </div>
  <div class="reset"><button id="resetBtn" type="button">Remettre à zéro…</button></div>
  <div id="dlg" role="dialog" aria-modal="true" aria-labelledby="dlgT"><div class="box">
    <h2 id="dlgT">Remettre les statistiques à zéro</h2>
    <p>Tous les totaux (visites, pages vues, vidéos, pays, provenance) seront <b>effacés définitivement</b>. Seules les visites faites
    <b>après</b> la remise à zéro seront comptées.</p>
    <p>Cette page est publique : elle ne peut pas effacer elle-même (sinon n'importe qui pourrait le faire). L'effacement se fait sur
    <b>GitHub</b>, où il faut taper un mot de confirmation :</p>
    <div id="dlgSteps"></div>
    <div class="row"><button id="dlgNo" type="button">Annuler</button><span id="dlgGo"></span></div>
  </div></div>
  <p class="note">Chiffres approximatifs. « Visite » = une arrivée sur le site (une page ouverte ou rechargée). « Visiteurs différents » =
  estimation par jour à partir de l'adresse IP anonymisée et du navigateur : le même visiteur revenu un autre jour est recompté, et
  plusieurs personnes derrière une même connexion peuvent n'en faire qu'une. Les robots connus sont écartés. Un bloqueur de publicité
  ou le réglage « ne pas me suivre » empêche de compter un visiteur. Les lectures de vidéos comptent les vidéos lancées avec le son
  ou ouvertes en plein écran (pas les vignettes muettes).</p>
</main>
<script>
var DATA = __DATA__;
var NAMES = DATA.names;
var DAYS = DATA.days;
var PERIOD = 30;

function el(id){ return document.getElementById(id); }
function esc(s){ return String(s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
function pad(n){ return n < 10 ? '0' + n : '' + n; }
function key(d){ return d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate()); }
function fr(n){ return Number(n).toLocaleString('fr-FR'); }

function prettyPage(n){
  if (NAMES.pages[n]) return NAMES.pages[n];
  return n.split('/').map(function(p){
    p = p.replace(/^(galerie|galeries|outils|evenements|evenement|dossiers)-/, '').replace(/-/g, ' ');
    return p.charAt(0).toUpperCase() + p.slice(1);
  }).join(' › ');
}
function prettyAction(n){
  if (n.indexOf('aide:') === 0) return 'Explication « ? » ouverte : ' + prettyPage(n.slice(5));
  return n;
}

function listDays(period){
  var out = [], today = new Date(), first = null;
  if (period === 0) {                                // « Tout » : depuis le premier jour enregistré
    var keys = Object.keys(DAYS).sort();
    if (!keys.length) return [];
    var p = keys[0].split('-'); first = new Date(+p[0], +p[1]-1, +p[2]);
    period = Math.max(1, Math.round((today - first) / 86400000) + 1);
  }
  for (var i = period - 1; i >= 0; i--) { var d = new Date(today); d.setDate(today.getDate() - i); out.push(key(d)); }
  return out;
}

function table(id, obj, fmt, total){
  var rows = Object.keys(obj).map(function(k){ return [k, obj[k]]; }).sort(function(a,b){ return b[1]-a[1]; }).slice(0, 15);
  if (!rows.length) { el(id).innerHTML = '<div class="empty">Rien sur cette période.</div>'; return; }
  var max = rows[0][1];
  el(id).innerHTML = '<table>' + rows.map(function(r){
    return '<tr><td>' + esc(fmt ? fmt(r[0]) : r[0]) + '</td><td class="b"><i style="width:' + Math.max(3, Math.round(r[1]/max*100)) + '%"></i></td><td class="v">' + fr(r[1]) + '</td></tr>';
  }).join('') + '</table>';
}

function render(){
  var days = listDays(PERIOD), sum = {visits:0, views:0, plays:0, visitors:0};
  var pages = {}, videos = {}, actions = {}, countries = {}, refs = {};
  days.forEach(function(d){
    var r = DAYS[d]; if (!r) return;
    sum.visits += r.visits; sum.views += r.views; sum.plays += r.plays; sum.visitors += r.visitors;
    [['pages',pages],['videos',videos],['actions',actions],['countries',countries],['refs',refs]].forEach(function(p){
      Object.keys(r[p[0]]||{}).forEach(function(k){ p[1][k] = (p[1][k]||0) + r[p[0]][k]; });
    });
  });
  el('kpis').innerHTML = [
    ['Visites', sum.visits], ['Pages vues', sum.views], ['Vidéos lancées', sum.plays], ['Visiteurs (par jour, cumulés)', sum.visitors]
  ].map(function(k){ return '<div class="card kpi"><div class="n">' + fr(k[1]) + '</div><div class="l">' + k[0] + '</div></div>'; }).join('');

  // graphique : barres = pages vues, ligne = visiteurs
  var W = 1000, H = 240, L = 40, B = 28, T = 10, n = days.length;
  var vals = days.map(function(d){ return DAYS[d] ? DAYS[d].views : 0; });
  var vis = days.map(function(d){ return DAYS[d] ? DAYS[d].visitors : 0; });
  var max = Math.max(1, Math.max.apply(null, vals), Math.max.apply(null, vis));
  var bw = (W - L) / Math.max(n, 1);
  var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Pages vues et visiteurs par jour">';
  [0, .5, 1].forEach(function(f){ var y = T + (H - T - B) * (1 - f);
    svg += '<line x1="' + L + '" x2="' + W + '" y1="' + y + '" y2="' + y + '" stroke="#2a2a2a"/><text x="' + (L-6) + '" y="' + (y+4) + '" fill="#888" font-size="11" text-anchor="end">' + fr(Math.round(max*f)) + '</text>'; });
  vals.forEach(function(v, i){ var h = (H - T - B) * v / max;
    svg += '<rect x="' + (L + i*bw + bw*0.15) + '" y="' + (H - B - h) + '" width="' + (bw*0.7) + '" height="' + h + '" rx="2" fill="#4ea1ef"><title>' + days[i] + ' : ' + v + ' pages vues, ' + vis[i] + ' visiteurs</title></rect>'; });
  var pts = vis.map(function(v, i){ return (L + i*bw + bw/2) + ',' + (H - B - (H - T - B) * v / max); }).join(' ');
  if (n > 1) svg += '<polyline points="' + pts + '" fill="none" stroke="#6fcf8d" stroke-width="2.5"/>';
  vis.forEach(function(v, i){ svg += '<circle cx="' + (L + i*bw + bw/2) + '" cy="' + (H - B - (H - T - B) * v / max) + '" r="' + (n > 45 ? 1.8 : 3) + '" fill="#6fcf8d"/>'; });
  var step = Math.max(1, Math.ceil(n / 8));
  days.forEach(function(d, i){ if (i % step === 0 || i === n-1) svg += '<text x="' + (L + i*bw + bw/2) + '" y="' + (H - 8) + '" fill="#888" font-size="11" text-anchor="middle">' + d.slice(8) + '/' + d.slice(5,7) + '</text>'; });
  el('chart').innerHTML = svg + '</svg>';

  table('t-pages', pages, prettyPage);
  table('t-videos', videos);
  table('t-refs', refs);
  table('t-countries', countries, function(c){ return NAMES.countries[c] ? NAMES.countries[c] + ' (' + c + ')' : (c === '??' ? 'Inconnu' : c); });
  table('t-actions', actions, prettyAction);

  Array.prototype.forEach.call(el('periods').children, function(b){ b.className = (+b.getAttribute('data-p') === PERIOD) ? 'on' : ''; });
}

el('upd').textContent = DATA.updated || '—';
if (DATA.reset_at) el('upd').insertAdjacentHTML('afterend', ' · compteurs remis à zéro le <b>' + esc(DATA.reset_at) + '</b>');

// Remise à zéro : confirmation avant d'ouvrir la page GitHub où le mot de confirmation est à taper
function actionsUrl() {
  var h = location.hostname;
  if (!/\.github\.io$/.test(h)) return '';
  var repo = location.pathname.split('/').filter(Boolean)[0] || '';
  return repo ? 'https://github.com/' + h.split('.')[0] + '/' + repo + '/actions/workflows/stats.yml' : '';
}
function closeDlg() { el('dlg').className = ''; }
el('resetBtn').onclick = function () {
  var url = actionsUrl();
  el('dlgSteps').innerHTML = url
    ? '<ol><li>Clique sur « Ouvrir la page des relevés » ci-dessous (elle s\'ouvre sur GitHub).</li>' +
      '<li>Clique sur <b>Run workflow</b> (à droite).</li>' +
      '<li>Dans la case, tape exactement : <code>REMISE A ZERO</code></li>' +
      '<li>Clique sur le bouton vert <b>Run workflow</b>, attends 30 secondes, puis recharge ce rapport.</li></ol>'
    : '<p>Dans le Terminal, sur ton Mac :</p><p><code>python3 stats-bunny.py --remise-a-zero</code></p><p>Le script te demandera de taper <code>REMISE A ZERO</code> pour confirmer.</p>';
  el('dlgGo').innerHTML = url ? '<a class="go" target="_blank" rel="noopener" href="' + url + '">Ouvrir la page des relevés</a>' : '';
  el('dlg').className = 'open';
};
el('dlgNo').onclick = closeDlg;
el('dlg').onclick = function (e) { if (e.target === el('dlg')) closeDlg(); };
document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeDlg(); });
if (/^\d{4}-\d\d-\d\d \d\d:\d\d$/.test(DATA.updated || '')) {
  var age = (Date.now() - new Date(DATA.updated.replace(' ', 'T')).getTime()) / 86400000;
  if (age > 2) el('warn').innerHTML += '<div class="warn">Dernier relevé il y a ' + Math.floor(age) + ' jours. Bunny ne garde ses journaux que 3 jours : si le relevé automatique est arrêté, des visites sont perdues. Relance le relevé (sur GitHub : onglet Actions, réactive le workflow puis « Run workflow »).</div>';
}
if (DATA.beacon_errors) el('warn').innerHTML += '<div class="warn">' + DATA.beacon_errors + ' demande(s) du site vers la petite image ont reçu une erreur : le fichier <b>v.gif</b> est-il bien dans le dossier <b>_mapt</b> de ton Storage Bunny, et ton site figure-t-il dans <b>Security &gt; Allowed referrers</b> de la zone ?</div>';
[[7,'7 jours'],[30,'30 jours'],[90,'90 jours'],[0,'Tout']].forEach(function(p){
  var b = document.createElement('button'); b.textContent = p[1]; b.setAttribute('data-p', p[0]);
  b.onclick = function(){ PERIOD = p[0]; render(); }; el('periods').appendChild(b);
});
if (!Object.keys(DAYS).length) el('warn').innerHTML += '<div class="warn">Aucune donnée pour le moment. Lance le script après quelques visites du site.</div>';
render();
</script>
</body>
</html>
'''


def build_report(state, path, demo=False):
    days = {}
    for day, rec in sorted(state['days'].items()):
        days[day] = {k: v for k, v in rec.items() if k != 'vset'}
    data = {'days': days, 'updated': ('EXEMPLE — données inventées' if demo else state.get('updated')),
            'beacon_errors': 0 if demo else state.get('beacon_errors', 0),
            'reset_at': None if demo else state.get('reset_at'),
            'names': {'pages': NOMS_PAGES, 'countries': NOMS_PAYS}}
    payload = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')   # évite de fermer la balise <script>
    html = REPORT_TEMPLATE.replace('__DATA__', payload)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)


def demo_state(tz):
    """Données INVENTÉES, seulement pour voir à quoi ressemble le rapport."""
    rnd = random.Random(7)
    state = new_state()
    today = dt.datetime.now(tz).date()
    pages = ['accueil', 'galeries', 'galeries/galerie-courtes-realisations', 'galeries/galerie-par-thematiques',
             'galeries/galerie-premieres-machines', 'galeries/galerie-ralentis', 'outils/outils-simulateur-acceleration',
             'outils/outils-chronometre', 'outils/outils-metronome', 'evenements', 'contact', 'dossiers']
    videos = ['StorieMAPT Danse1', 'StorieMAPT Burlesque1', 'griffe', 'rire char à voile', 'BONNE ANNEE 2021 ok',
              'Etretat', 'Phare StMathieu1', 'Penseur']
    refs = ['(accès direct)', '(accès direct)', 'instagram.com', 'facebook.com', 'pixelsenscene.fr', 'google.com']
    for i in range(75):
        day = (today - dt.timedelta(days=74 - i)).strftime('%Y-%m-%d')
        base = rnd.randint(4, 22) + (14 if i in (30, 31, 58) else 0)
        rec = empty_day()
        rec['vset'] = []
        rec['visitors'] = max(1, int(base * rnd.uniform(.6, .9)))
        rec['visits'] = base
        for _ in range(base):
            bump(rec['refs'], rnd.choice(refs))
            for _ in range(rnd.randint(1, 5)):
                rec['views'] += 1
                bump(rec['pages'], rnd.choice(pages))
            if rnd.random() < .55:
                rec['plays'] += 1
                bump(rec['videos'], rnd.choice(videos))
            if rnd.random() < .12:
                bump(rec['actions'], 'aide:outils/' + rnd.choice(['outils-chronometre', 'outils-simulateur-acceleration']))
        for _ in range(rec['visitors']):
            bump(rec['countries'], rnd.choice(['FR', 'FR', 'FR', 'FR', 'BE', 'CH', 'CA', 'DE', 'US', '??']))
        state['days'][day] = rec
    state['updated'] = dt.datetime.now(tz).strftime('%Y-%m-%d %H:%M')
    return state


# ----------------------------------------------------------------------------------------------------------------
# PROGRAMME
# ----------------------------------------------------------------------------------------------------------------
def cmd_init():
    print('Configuration (enregistrée dans %s, lisible par toi seul).' % CONFIG_FILE)
    print('Le numéro de zone : dans Bunny, ouvre ta zone (Pull Zone) : le numéro figure dans l\'adresse de la page '
          '(.../pullzones/NUMÉRO/...) et dans les réglages de la zone.')
    zone = input('Numéro de la zone Bunny : ').strip()
    if not zone.isdigit():
        print('Le numéro de zone ne contient que des chiffres.')
        sys.exit(1)
    print('La clé d\'accès : Bunny > Account settings > API Keys. (Ce que tu tapes ne s\'affiche pas.)')
    key = getpass.getpass('Clé d\'accès Bunny : ').strip()
    if not key:
        print('Clé vide : rien n\'a été enregistré.')
        sys.exit(1)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(str(DATA_DIR), 0o700)
    except OSError:
        pass
    save_json(CONFIG_FILE, {'pullzone_id': zone, 'api_key': key}, private=True)
    print('Enregistré. Tu peux lancer :  python3 stats-bunny.py')


def open_report(path):
    try:
        webbrowser.open('file://' + str(path))
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description='Statistiques de fréquentation maison (journaux Bunny).')
    ap.add_argument('--init', action='store_true', help='enregistre le numéro de zone et la clé d\'accès Bunny')
    ap.add_argument('--rapport', action='store_true', help='refait le rapport sans interroger Bunny')
    ap.add_argument('--demo', action='store_true', help='rapport d\'exemple avec des données inventées')
    ap.add_argument('--sans-ouvrir', action='store_true', help='n\'ouvre pas le rapport dans le navigateur')
    ap.add_argument('--remise-a-zero', action='store_true', help='EFFACE tous les totaux (confirmation demandée)')
    ap.add_argument('--confirmer', default=None, help='mot de confirmation, pour une exécution automatique (sinon il est demandé)')
    args = ap.parse_args()
    tz = get_tz()

    if args.init:
        cmd_init()
        return
    if args.remise_a_zero:
        cmd_reset(args.confirmer, tz)
        return
    if args.demo:
        demo_file = DATA_DIR / 'rapport-EXEMPLE.html'
        build_report(demo_state(tz), demo_file, demo=True)
        print('Rapport d\'exemple : %s' % demo_file)
        if not args.sans_ouvrir:
            open_report(demo_file)
        return

    state = load_json(STATE_FILE, None) or new_state()
    if not args.rapport:
        cfg = load_config()
        if not cfg.get('api_key') or not cfg.get('pullzone_id'):
            print('Pas encore configuré. Lance d\'abord :  python3 stats-bunny.py --init')
            sys.exit(1)
        try:
            total, counted, bots, errors = update_from_bunny(cfg, state, tz)
        except BunnyError as e:
            print('Erreur : %s' % e)
            sys.exit(1)
        save_json(STATE_FILE, state)
        print('Relevé terminé : %d demande(s) lue(s), %d comptée(s), %d robot(s) écarté(s).' % (total, counted, bots))
        if errors:
            print('Attention : %d demande(s) envoyées par le site ont reçu une erreur. Vérifie (1) que v.gif est bien dans le dossier '
                  '_mapt de ton Storage Bunny (erreur 404), (2) que ton site figure dans les adresses autorisées : zone Bunny > '
                  'Security > Allowed referrers (erreur 403).' % errors)
        if total == 0:
            print('Aucune demande trouvée. Si le site vient d\'être mis en ligne avec stats.js, c\'est normal : attends quelques visites.')
    build_report(state, REPORT_FILE)
    print('Rapport : %s' % REPORT_FILE)
    if not args.sans_ouvrir:
        open_report(REPORT_FILE)


if __name__ == '__main__':
    main()
