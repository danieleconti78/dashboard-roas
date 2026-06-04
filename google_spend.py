"""Legge la spesa Google dai fogli esportati dagli script Google Ads (tab 'spesa', 'spesa_ais').
Parsa il nome campagna -> (corso, tipo). Ritorna gspend_day[(course,tipo,date)] = costo."""
import datetime as dt, re
from collections import defaultdict
from google.oauth2 import service_account
from googleapiclient.discovery import build

# fonti: (spreadsheet_id, tab). Aggiungere qui il foglio AIS quando pronto.
SOURCES = [
    ("1M7fuEDjDAoUeF17oJqlEx84JJp6sN36wIbdl6BYb1Zo", "spesa"),      # Calcio (SAFI SRL)
    ("1UsLGdCzicSIdr2V0ub3B7PzL7IMLQdUzCM184aH3LBs", "spesa"),      # Sportiva (AIS)
]

# token nel nome campagna -> corso (specifico prima del generico)
CAMP2COURSE = [
    ("istruttore_scuola_calcio", "Istruttore Scuola Calcio"), ("scuola_calcio", "Istruttore Scuola Calcio"),
    ("match_analyst", "Match Analyst a 11"), ("analyst", "Match Analyst a 11"),
    ("osservatore", "Osservatore"), ("direttore", "Direttore Sportivo"), ("portieri", "Portieri"),
    # Sportiva (per quando arriva il foglio AIS)
    ("reformer", "Pilates Reformer"), ("matwork", "Pilates Matwork"), ("mental", "Mental Coach"),
    ("running", "Istruttore Running"), ("volley", "Match Analyst Pallavolo"), ("basket", "Match Analyst Basket"),
]


def _tipo(name):
    n = name.lower()
    if "p-max" in n or "pmax" in n or "p_max" in n or "performance" in n: return "PMax"
    if "search" in n: return "Search"
    if "demand" in n or "demgen" in n or "dem_gen" in n: return "Demand Gen"
    return "Altro"


def _corso(name):
    n = re.sub(r"[^a-z0-9]+", "_", name.lower())
    return next((c for tok, c in CAMP2COURSE if tok in n), None)


def _num(x):
    try: return float(str(x).replace("€", "").replace(".", "").replace(",", ".")) if isinstance(x, str) else float(x)
    except Exception: return 0.0


def _date(s):
    try: return dt.date.fromisoformat(str(s)[:10])
    except Exception:
        try: return dt.datetime.strptime(str(s).split()[0], "%d/%m/%Y").date()
        except Exception: return None


def read_google_spend():
    creds = service_account.Credentials.from_service_account_file(
        "secrets/key.json", scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    gspend = defaultdict(float); unmapped = defaultdict(float)
    for sid, tab in SOURCES:
        try:
            rows = svc.spreadsheets().values().get(spreadsheetId=sid, range=f"{tab}!A2:C").execute().get("values", [])
        except Exception as e:
            print(f"  (salto {tab}: {str(e)[:60]})"); continue
        for r in rows:
            if len(r) < 3: continue
            d = _date(r[0]); cost = _num(r[2]); course = _corso(r[1])
            if d is None or not cost: continue
            if course: gspend[(course, _tipo(r[1]), d)] += cost
            else: unmapped[r[1]] += cost
    return gspend, unmapped


if __name__ == "__main__":
    g, un = read_google_spend()
    tot = defaultdict(float)
    for (c, tp, d), v in g.items(): tot[(c, tp)] += v
    print(f"{'CORSO':26}{'TIPO':12}{'SPESA':>10}")
    for (c, tp), v in sorted(tot.items(), key=lambda x: -x[1]):
        print(f"{c[:26]:26}{tp:12}{v:>10.0f}")
    if un: print("NON mappate:", dict(un))
