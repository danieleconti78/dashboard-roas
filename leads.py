"""Legge i tab lead per-corso (Meta Lead Ads) e conta lead per corso, con contatti normalizzati."""
import datetime as dt
from collections import defaultdict
from google.oauth2 import service_account
from googleapiclient.discovery import build
from contacts import contact_keys

AIC = "1ZQbXj_h8UPW_T00C2oYt9bLr7etzL0gteUNQ-XEIitQ"
AIS = "1DUzQpmtEogCoJQTpcuH__aPtTxJ_ydTgzXmfP8LdDYk"
PRES = "1hmRAXDxwdVgU0jZGiOZCuWuWhF0QTfLnyQ0O3CA9qfs"   # foglio presenza

# tab lead -> corso canonico (solo corsi pubblicizzati attivi)
TABS = {
    AIC: {"Osservatore": "Osservatore", "Portieri": "Portieri",
          "Match_Analyst": "Match Analyst a 11", "Direttore": "Direttore Sportivo",
          "Direttore_ott_25 (4)": "Direttore Sportivo",  # continuazione: 'Direttore' si ferma al 27/05
          "Istruttore_SC": "Istruttore Scuola Calcio"},
    AIS: {"Match_Volley": "Match Analyst Pallavolo", "Match_Basket": "Match Analyst Basket",
          "Mental_Coach": "Mental Coach", "Pilates_Mat": "Pilates Matwork",
          "Pilates_Ref": "Pilates Reformer", "Istr_Running": "Istruttore Running",
          "Pres_Ref_MI": "Reformer presenza Milano",    # presenza Milano
          "Pres_Mat_TO": "Reformer presenza Torino"},   # presenza Torino
    PRES: {"OFF_REF_PRES": "Reformer presenza Prato"},   # presenza Prato (il grosso del volume)
}


def _svc():
    creds = service_account.Credentials.from_service_account_file(
        "secrets/key.json", scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _date(v):
    s = str(v).strip()
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])   # "2026-02-25T..." -> 2026-02-25
    except ValueError:
        for fmt in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                return dt.datetime.strptime(s.split()[0], fmt).date()
            except (ValueError, IndexError):
                pass
    return None


def read_leads():
    """Ritorna: leads_day[(course,date)]=n, e lead_first[course][chiave]=data primo lead."""
    svc = _svc()
    leads_day = defaultdict(int)
    lead_first = defaultdict(dict)   # course -> {chiave contatto: data lead più vecchia}
    seen = set()                     # id lead già contati (dedup tra tab spezzati)
    for sid, tabs in TABS.items():
        for tab, course in tabs.items():
            try:
                rows = svc.spreadsheets().values().get(
                    spreadsheetId=sid, range=f"{tab}!A:O").execute().get("values", [])
            except Exception as e:
                print(f"  ERR {tab}: {e}")
                continue
            # A:O -> id=idx0, created_time=idx1(B), name=idx12(M), email=idx13(N), phone=idx14(O)
            for r in rows:
                cid = r[0] if len(r) > 0 else None
                d = _date(r[1]) if len(r) > 1 else None
                if d is None:        # salta header / righe senza data valida
                    continue
                if cid:              # dedup per id lead (evita doppi tra tab spezzati)
                    if cid in seen:
                        continue
                    seen.add(cid)
                name = r[12] if len(r) > 12 else None
                email = r[13] if len(r) > 13 else None
                phone = r[14] if len(r) > 14 else None
                if "test@meta" in str(email or "") or "<test" in str(name or ""):
                    continue                         # scarta i lead di test di Meta
                leads_day[(course, d)] += 1
                fm = lead_first[course]
                for k in contact_keys(email, phone, name):
                    if k not in fm or d < fm[k]:
                        fm[k] = d
    return leads_day, lead_first


if __name__ == "__main__":
    leads_day, lead_first = read_leads()
    tot = defaultdict(int)
    for (c, d), n in leads_day.items():
        tot[c] += n
    print(f"{'CORSO':28} {'LEAD TOT':>9} {'contatti uniq':>14}")
    for c, n in sorted(tot.items(), key=lambda x: -x[1]):
        print(f"{c:28} {n:>9} {len(lead_first[c]):>14}")
