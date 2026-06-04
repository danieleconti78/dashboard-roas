"""Scarica spesa Meta a livello inserzione (giornaliera) e la attribuisce per corso."""
import json, ssl, time, urllib.parse, urllib.request, certifi
from collections import defaultdict
from courses import match_course

TOKEN = open("secrets/meta_token.txt").read().strip()
API = "https://graph.facebook.com/v24.0"
CTX = ssl.create_default_context(cafile=certifi.where())
ACCOUNTS = {"CALCIO": "act_505303364156004", "SPORTIVA": "act_9179156665539364"}


def get_all(path, params):
    """Ritorna tutte le righe seguendo la paginazione."""
    params = {**params, "access_token": TOKEN}
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    rows = []
    RETRIES = 7
    while url:
        data = None
        for attempt in range(RETRIES):
            try:
                with urllib.request.urlopen(url, context=CTX) as r:
                    data = json.load(r)
                break
            except urllib.error.HTTPError as e:
                body = ""
                try: body = e.read().decode()
                except Exception: pass
                if '"code":190' in body or "expired" in body.lower():
                    raise RuntimeError("TOKEN META SCADUTO: rigenera secrets/meta_token.txt "
                                       "(o usa il token permanente System User).")
                if e.code in (400, 403, 429, 500, 503) and attempt < RETRIES - 1:
                    time.sleep(min(60, 10 * (attempt + 1)))   # backoff (rate-limit Meta)
                    continue
                raise RuntimeError(f"Meta API {e.code}: {body[:200]}")
        if data is None:
            raise RuntimeError(f"Meta API: nessuna risposta valida per {path} dopo {RETRIES} tentativi")
        rows.extend(data.get("data", []))
        url = (data.get("paging") or {}).get("next")
        time.sleep(0.3)
    return rows


import datetime as dt


def _chunks(span_days, chunk=30):
    """Finestre di max 30gg (Meta rifiuta ad-level giornaliero su periodi lunghi)."""
    until = dt.date.today() - dt.timedelta(days=1)      # come 'last_Nd' (esclude oggi)
    since = until - dt.timedelta(days=span_days - 1)
    out, s = [], since
    while s <= until:
        e = min(s + dt.timedelta(days=chunk - 1), until)
        out.append((s, e)); s = e + dt.timedelta(days=1)
    return out


def _tr(s, e):
    return json.dumps({"since": s.isoformat(), "until": e.isoformat()})


def account_total(acc, s, e):
    """Spesa totale account nel range (leggera, per validare la pull ad-level)."""
    d = get_all(f"{acc}/insights", {"fields": "spend", "time_range": _tr(s, e)})
    return sum(float(r.get("spend", 0) or 0) for r in d)


def fetch_spend(span_days=60):
    """Spesa ad-level giornaliera su span_days, scaricata a blocchi di 30gg e validata
    per blocco (somma ad-level == totale account, altrimenti ritenta)."""
    per_course = defaultdict(float); per_day = defaultdict(float); unattr = defaultdict(float)
    for account, acc in ACCOUNTS.items():
        for (s, e) in _chunks(span_days):
            expected = account_total(acc, s, e)
            rows, got = [], -1
            for attempt in range(6):
                rows = get_all(f"{acc}/insights", {
                    "fields": "ad_name,adset_name,spend", "level": "ad",
                    "time_range": _tr(s, e), "time_increment": "1", "limit": "1000"})
                got = sum(float(r.get("spend", 0) or 0) for r in rows)
                if expected == 0 or abs(got - expected) / expected <= 0.01:
                    break
                time.sleep(8 * (attempt + 1))
            if expected and abs(got - expected) / expected > 0.01:
                raise RuntimeError(f"{account} {s}..{e}: ad-level {got:.0f} != totale {expected:.0f}")
            for r in rows:
                spend = float(r.get("spend", 0) or 0)
                course = match_course(account, r.get("ad_name"), r.get("adset_name"))
                if course is None:
                    unattr[f"{account}: {r.get('adset_name')}"] += spend
                else:
                    per_course[(account, course)] += spend
                    per_day[(account, course, r.get("date_start"))] += spend
    return per_course, per_day, unattr


if __name__ == "__main__":
    per_course, per_day, unattr = fetch_spend(30)
    tot_attr = sum(per_course.values())
    tot_un = sum(unattr.values())
    print("=== SPESA ATTRIBUITA PER CORSO (ultimi 30 giorni) ===")
    for (acc, course), s in sorted(per_course.items(), key=lambda x: -x[1]):
        print(f"  {acc:9} {course:28} € {s:>9.2f}")
    print(f"\nTotale attribuito:     € {tot_attr:>10.2f}")
    print(f"Totale NON attribuito: € {tot_un:>10.2f}  ({tot_un/(tot_attr+tot_un)*100:.1f}%)")
    if unattr:
        print("\n  Adset non attribuiti (da capire insieme):")
        for name, s in sorted(unattr.items(), key=lambda x: -x[1]):
            if s > 0:
                print(f"    € {s:>9.2f}  {name}")
