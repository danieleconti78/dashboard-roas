"""Lead Google da 'Sito AIC' via utm_campaign (g_ads_search/pmax_<corso>). Solo Calcio."""
import datetime as dt, re
from collections import defaultdict
from google.oauth2 import service_account
from googleapiclient.discovery import build
from contacts import contact_keys

AIC = "1ZQbXj_h8UPW_T00C2oYt9bLr7etzL0gteUNQ-XEIitQ"
# token nel utm_campaign -> corso canonico
UTM2COURSE = [
    ("analyst", "Match Analyst a 11"), ("match", "Match Analyst a 11"),
    ("osservatore", "Osservatore"), ("direttore", "Direttore Sportivo"),
    ("portieri", "Portieri"), ("istruttore_scuola_calcio", "Istruttore Scuola Calcio"),
    ("scuola_calcio", "Istruttore Scuola Calcio"), ("mental", "Mental Coach"),
]

def _date(s):
    s = str(s).strip()
    try: return dt.datetime.strptime(s.split()[0], "%d/%m/%Y").date()
    except Exception:
        try: return dt.date.fromisoformat(s[:10])
        except Exception: return None

def _tipo(utm):
    if "search" in utm: return "Search"
    if "pmax" in utm or "performance_max" in utm: return "PMax"
    if "demand" in utm or "demgen" in utm or "demand_gen" in utm: return "Demand Gen"
    return "Altro"


def read_google_leads():
    """Ritorna: gday[(course,date)]=n, gtype[course]={tipo:n}, gfirst[course]={chiave:(data,tipo)},
    gtypeday[(course,tipo,date)]=n. Sito AIC: A=DATA B=NOME C=MAIL D=TELEFONO ... K=utm_campaign."""
    creds = service_account.Credentials.from_service_account_file(
        "secrets/key.json", scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    rows = svc.spreadsheets().values().get(spreadsheetId=AIC, range="Sito AIC!A2:K").execute().get("values", [])
    gday = defaultdict(int); gtype = defaultdict(lambda: defaultdict(int))
    gfirst = defaultdict(dict); gtypeday = defaultdict(int)
    for r in rows:
        d = _date(r[0]) if len(r) > 0 else None
        utm = (r[10].strip().lower() if len(r) > 10 and r[10] else "")
        if d is None or not ("g_ads" in utm or "gads" in utm):   # Google: g_ads_* o *_gads (es. pmax_match_gads)
            continue
        tipo = _tipo(utm)
        course = next((c for tok, c in UTM2COURSE if tok in utm), None)
        if course is None:
            continue
        gday[(course, d)] += 1
        gtype[course][tipo] += 1
        gtypeday[(course, tipo, d)] += 1
        nome = r[1] if len(r) > 1 else None
        mail = r[2] if len(r) > 2 else None
        tel = r[3] if len(r) > 3 else None
        fm = gfirst[course]
        for k in contact_keys(mail, tel, nome):
            if k not in fm or d < fm[k][0]:
                fm[k] = (d, tipo)
    return gday, gtype, gfirst, gtypeday

if __name__ == "__main__":
    gday, gtype, gfirst, gtypeday = read_google_leads()
    tot = defaultdict(int)
    for (c, d), n in gday.items(): tot[c] += n
    print(f"{'CORSO':28}{'LEAD GOOGLE(tot)':>17}  tipi")
    for c, n in sorted(tot.items(), key=lambda x: -x[1]):
        print(f"{c:28}{n:>17}  {dict(gtype[c])}")
