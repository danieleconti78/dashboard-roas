"""Lead dai fogli SITO (Sito AIC + Sito_AIS).
- Lead con UTM g_ads/gads -> canale GOOGLE, corso preso dall'UTM (la campagna).
- Lead senza UTM        -> canale SEO/ORGANICO, corso preso dalla colonna E (CORSO, primo se multipli)."""
import datetime as dt
import re
from collections import defaultdict
from google.oauth2 import service_account
from googleapiclient.discovery import build
from contacts import contact_keys

AIC = "1ZQbXj_h8UPW_T00C2oYt9bLr7etzL0gteUNQ-XEIitQ"
AIS = "1TAYJAc9rPyEoOjwGTTN8CpKVOrfWa9OKbqOInNPRZnM"
SITES = [(AIC, "Sito AIC")]   # AIS: vedi _read_site_ais (foglio AIS_LEADS_2027, schema AUTO + Origine_lead)

# slug colonna E -> corso (per i lead SEO/organici)
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
# token nell'UTM -> corso (per i lead GOOGLE)
UTMC = [
    ("volley", "Match Analyst Pallavolo"), ("pallavolo", "Match Analyst Pallavolo"),
    ("basket", "Match Analyst Basket"), ("analyst", "Match Analyst a 11"), ("match", "Match Analyst a 11"),
    ("osservatore", "Osservatore"), ("direttore", "Direttore Sportivo"), ("portieri", "Portieri"),
    ("istruttore_scuola_calcio", "Istruttore Scuola Calcio"), ("scuola_calcio", "Istruttore Scuola Calcio"),
    ("mental", "Mental Coach"), ("matwork", "Pilates Matwork"), ("reformer", "Pilates Reformer"),
    ("running", "Istruttore Running"),
]


def site_course(cell):
    first = str(cell or "").split(",")[0].strip().lower()
    return next((c for tok, c in SLUG if tok in first), None)


def utm_course(utm):
    n = utm.lower()
    return next((c for tok, c in UTMC if tok in n), None)


def _tipo(utm):
    if "pmax" in utm or "p-max" in utm or "p_max" in utm: return "PMax"
    if "demand" in utm or "demgen" in utm or re.search(r"(^|_)dg(_|$)", utm): return "Demand Gen"
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
    gday = defaultdict(int); gtype = defaultdict(lambda: defaultdict(int))
    gtypeday = defaultdict(int); gfirst = defaultdict(dict)
    seo_day = defaultdict(int); seofirst = defaultdict(dict)
    for sid, tab in SITES:
        try:
            rows = svc.spreadsheets().values().get(spreadsheetId=sid, range=f"{tab}!A2:K").execute().get("values", [])
        except Exception as e:
            print(f"  (salto {tab}: {str(e)[:50]})"); continue
        for r in rows:                              # A=DATA B=NOME C=MAIL D=TEL E=CORSO ... K=utm
            d = _date(r[0]) if r else None
            if d is None: continue
            utm = (r[10].strip().lower() if len(r) > 10 and r[10] else "")
            keys = contact_keys(r[2] if len(r) > 2 else None, r[3] if len(r) > 3 else None, r[1] if len(r) > 1 else None)
            if "g_ads" in utm or "gads" in utm:     # GOOGLE: corso dall'UTM
                course = utm_course(utm)
                if course is None: continue
                tp = _tipo(utm)
                gday[(course, d)] += 1; gtype[course][tp] += 1; gtypeday[(course, tp, d)] += 1
                fm = gfirst[course]
                for k in keys:
                    if k not in fm or d < fm[k][0]: fm[k] = (d, tp)
            else:                                   # SEO/ORGANICO: corso dalla col E
                course = site_course(r[4]) if len(r) > 4 else None
                if course is None: continue
                seo_day[(course, d)] += 1
                fm = seofirst[course]
                for k in keys:
                    if k not in fm or d < fm[k]: fm[k] = d
    _read_site_ais(svc, gday, gtype, gtypeday, gfirst, seo_day, seofirst)
    return gday, gtype, gtypeday, gfirst, seo_day, seofirst


def _read_site_ais(svc, gday, gtype, gtypeday, gfirst, seo_day, seofirst):
    """Sito AIS sul foglio AIS_LEADS_2027: date/UTM da 'Origine_lead' (Fonte=Sito), contatti e corso da 'Sito_AIS_auto'."""
    from leads import batch_get, AUTO_TABS
    g = batch_get(svc, AIS, ["Origine_lead!A2:K", "Sito_AIS_auto!A2:F"])
    auto = {}
    for r in g.get("Sito_AIS_auto!A2:F", []):
        if len(r) > 5 and r[5]:
            auto[r[5].strip()] = (contact_keys(r[3] if len(r) > 3 else None, r[2] if len(r) > 2 else None, r[1]),
                                  str(r[4]).replace("Sito AIS:", "").strip())
    tab2course = AUTO_TABS.get(AIS, {})
    for r in g.get("Origine_lead!A2:K", []):
        if len(r) < 4 or r[3] != "Sito":
            continue
        d = _date(r[2]); lid = r[0].strip()
        if d is None: continue
        utm = " ".join(str(x) for x in r[6:9]).strip().lower() if len(r) > 6 else ""
        keys, corso_cell = auto.get(lid, ([], ""))
        if "g_ads" in utm or "google_ads" in utm or "gads" in utm:
            course = utm_course(utm)
            if course is None: continue
            tp = _tipo(utm)
            gday[(course, d)] += 1; gtype[course][tp] += 1; gtypeday[(course, tp, d)] += 1
            fm = gfirst[course]
            for k in keys:
                if k not in fm or d < fm[k][0]: fm[k] = (d, tp)
        else:
            course = site_course(corso_cell) or tab2course.get(r[1])
            if course is None: continue
            seo_day[(course, d)] += 1
            fm = seofirst[course]
            for k in keys:
                if k not in fm or d < fm[k]: fm[k] = d


if __name__ == "__main__":
    gday, gtype, gtd, gf, seo, sf = read_site()
    tg = defaultdict(int); ts = defaultdict(int)
    for (c, d), n in gday.items(): tg[c] += n
    for (c, d), n in seo.items(): ts[c] += n
    print(f"{'CORSO':28}{'GOOGLE(utm)':>12}{'SEO/organ.':>12}")
    for c in sorted(set(tg) | set(ts), key=lambda x: -(tg.get(x, 0) + ts.get(x, 0))):
        print(f"{c[:28]:28}{tg.get(c,0):>12}{ts.get(c,0):>12}")
