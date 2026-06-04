"""Lead dai fogli SITO (Sito AIC calcio + Sito_AIS sportiva): col E=CORSO (primo se multipli),
col K=utm_campaign. Ritorna: lead sito totali per corso (organico+ads) e il sottoinsieme Google."""
import datetime as dt
from collections import defaultdict
from google.oauth2 import service_account
from googleapiclient.discovery import build
from contacts import contact_keys

AIC = "1ZQbXj_h8UPW_T00C2oYt9bLr7etzL0gteUNQ-XEIitQ"
AIS = "1DUzQpmtEogCoJQTpcuH__aPtTxJ_ydTgzXmfP8LdDYk"
SITES = [(AIC, "Sito AIC"), (AIS, "Sito_AIS")]

# slug col E -> corso canonico (ordine specifico->generico)
SLUG = [
    ("osservatore", "Osservatore"), ("mental", "Mental Coach"),
    ("basket", "Match Analyst Basket"), ("pallavolo", "Match Analyst Pallavolo"), ("volley", "Match Analyst Pallavolo"),
    ("match-analyst", "Match Analyst a 11"), ("match analyst", "Match Analyst a 11"),
    ("direttore", "Direttore Sportivo"), ("portieri", "Portieri"),
    ("scuola-calcio", "Istruttore Scuola Calcio"), ("scuola calcio", "Istruttore Scuola Calcio"),
    ("matwork", "Pilates Matwork"), ("reformer", "Pilates Reformer"),
    ("running", "Istruttore Running"), ("personal", "Personal Trainer"),
    ("posturale", "Ginnastica Posturale"), ("ginnastica", "Ginnastica Posturale"),
    ("minivolley", "Istruttore Mini Volley"), ("mini-volley", "Istruttore Mini Volley"),
    ("yoga", "Istruttore Yoga"), ("tennis", "Istruttore Tennis"), ("padel", "Istruttore Padel"),
    ("walking", "Istruttore Nordik e Walking"), ("nordic", "Istruttore Nordik e Walking"), ("nordik", "Istruttore Nordik e Walking"),
    ("bodybuilding", "Istruttore Bodybuilding 1° livello"), ("massaggio", "Massaggio Sportivo"),
    ("prima-squadra", "Prima Squadra a 11"), ("prima squadra", "Prima Squadra a 11"),
    ("settore-giovanile", "Settore Giovanile a 11"), ("settore giovanile", "Settore Giovanile a 11"),
    ("futsal", "Istruttore Futsal (a 5)"), ("team-leader", "Team Leader"), ("team leader", "Team Leader"),
]


def site_course(cell):
    first = str(cell or "").split(",")[0].strip().lower()
    return next((c for tok, c in SLUG if tok in first), None)


def _tipo(utm):
    if "pmax" in utm or "p-max" in utm or "p_max" in utm: return "PMax"
    if "search" in utm: return "Search"
    if "demand" in utm or "demgen" in utm: return "Demand Gen"
    return "Search"


def _date(s):
    s = str(s).strip()
    try: return dt.datetime.strptime(s.split()[0], "%d/%m/%Y").date()
    except Exception:
        try: return dt.date.fromisoformat(s[:10])
        except Exception: return None


def read_site():
    creds = service_account.Credentials.from_service_account_file(
        "secrets/key.json", scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    sito_day = defaultdict(int)                          # lead sito TOTALI (organico+ads) per (corso,data)
    gday = defaultdict(int); gtype = defaultdict(lambda: defaultdict(int))
    gtypeday = defaultdict(int); gfirst = defaultdict(dict)
    for sid, tab in SITES:
        try:
            rows = svc.spreadsheets().values().get(spreadsheetId=sid, range=f"{tab}!A2:K").execute().get("values", [])
        except Exception as e:
            print(f"  (salto {tab}: {str(e)[:50]})"); continue
        for r in rows:                                  # A=DATA B=NOME C=MAIL D=TEL E=CORSO ... K=utm
            d = _date(r[0]) if r else None
            course = site_course(r[4]) if len(r) > 4 else None
            if d is None or course is None:
                continue
            sito_day[(course, d)] += 1
            utm = (r[10].strip().lower() if len(r) > 10 and r[10] else "")
            if "g_ads" in utm or "gads" in utm:         # sottoinsieme Google
                tp = _tipo(utm)
                gday[(course, d)] += 1
                gtype[course][tp] += 1
                gtypeday[(course, tp, d)] += 1
                fm = gfirst[course]
                for k in contact_keys(r[2] if len(r) > 2 else None, r[3] if len(r) > 3 else None, r[1] if len(r) > 1 else None):
                    if k not in fm or d < fm[k][0]:
                        fm[k] = (d, tp)
    return sito_day, gday, gtype, gtypeday, gfirst


if __name__ == "__main__":
    sito, gday, gtype, gtd, gf = read_site()
    ts = defaultdict(int); tg = defaultdict(int)
    for (c, d), n in sito.items(): ts[c] += n
    for (c, d), n in gday.items(): tg[c] += n
    print(f"{'CORSO':28}{'LEAD SITO':>11}{'di cui Google':>14}")
    for c in sorted(ts, key=lambda x: -ts[x]):
        print(f"{c[:28]:28}{ts[c]:>11}{tg.get(c,0):>14}")
