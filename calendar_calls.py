"""Legge le call fissate dal calendario 'Accademia Italiana Sportiva' e le attribuisce al corso."""
import datetime as dt, re
from collections import defaultdict
from google.oauth2 import service_account
from googleapiclient.discovery import build

CAL = "accademiaitalianasportiva@gmail.com"
# (regex su titolo normalizzato, corso). Ordine: specifico -> generico. "corso più probabile".
RULES = [
    (r"\bvolley\b", "Match Analyst Pallavolo"), (r"\bbasket\b", "Match Analyst Basket"),
    (r"\bmental\b", "Mental Coach"), (r"\bfutsal\b", "Istruttore Futsal (a 5)"),
    (r"\brunn?\b|running", "Istruttore Running"),
    (r"\bref\b|reformer", "Pilates Reformer"), (r"\bpilates\b|matwork|\bmat\b", "Pilates Matwork"),
    (r"\bpersonal\b", "Personal Trainer"),
    (r"\btennis\b", "Istruttore Tennis"), (r"\bpadel\b", "Istruttore Padel"),
    (r"nordic|nordik|walking", "Istruttore Nordik e Walking"), (r"\byoga\b", "Istruttore Yoga"),
    (r"bodybuilding|body building", "Istruttore Bodybuilding 1° livello"),
    (r"massaggio", "Massaggio Sportivo"), (r"posturale|ginnastica", "Ginnastica Posturale"),
    (r"sett?\s*giov|settore giovanile", "Settore Giovanile a 11"),
    (r"prima\s*sq|prima squadra", "Prima Squadra a 11"),
    (r"osservatore|\boss\b", "Osservatore"),
    (r"direttore|\bd\s*s\b|\bds\b", "Direttore Sportivo"),
    (r"portieri|\bport\b", "Portieri"),
    (r"istr\s*sc|istru\s*sc|scuola calcio|\bisc\b", "Istruttore Scuola Calcio"),
    (r"\bmatch\b|analyst", "Match Analyst a 11"),
    (r"\bistr\b|istruttore", "Istruttore Scuola Calcio"),
]

def course_of(title):
    n = re.sub(r"[^a-z0-9]+", " ", (title or "").lower())
    for pat, c in RULES:
        if re.search(pat, n):
            return c
    return None

def _svc():
    creds = service_account.Credentials.from_service_account_file(
        "secrets/key.json", scopes=["https://www.googleapis.com/auth/calendar.readonly"])
    return build("calendar", "v3", credentials=creds, cache_discovery=False)

def read_calls(days=70):
    svc = _svc()
    end = dt.datetime.utcnow() + dt.timedelta(days=1)
    start = end - dt.timedelta(days=days+1)
    calls = defaultdict(int); unmatched = []
    page = None
    while True:
        r = svc.events().list(calendarId=CAL, timeMin=start.isoformat()+"Z", timeMax=end.isoformat()+"Z",
                              singleEvents=True, maxResults=2500, pageToken=page).execute()
        for e in r.get("items", []):
            s = e.get("start", {}); ds = s.get("date") or (s.get("dateTime","")[:10])
            try: d = dt.date.fromisoformat(ds)
            except Exception: continue
            c = course_of(e.get("summary"))
            if c: calls[(c, d)] += 1
            else: unmatched.append(e.get("summary"))
        page = r.get("nextPageToken")
        if not page: break
    return calls, unmatched

if __name__ == "__main__":
    calls, un = read_calls(70)
    tot = defaultdict(int)
    for (c, d), n in calls.items(): tot[c] += n
    print(f"{'CORSO':30}{'CALL (70gg)':>12}")
    for c, n in sorted(tot.items(), key=lambda x: -x[1]): print(f"{c:30}{n:>12}")
    print(f"\nNON riconosciute: {len(un)}")
    for t in un[:15]: print("   ?", t)
