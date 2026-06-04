"""Dataset dashboard: spesa Meta + incassi/fatturato + lead Meta&Google, per corso/giorno.
Serie giornaliere su 30gg: il front-end calcola qualsiasi intervallo e i totali per accademia."""
import json, datetime as dt
from collections import defaultdict
from google.oauth2 import service_account
from googleapiclient.discovery import build as gbuild
from courses import match_sheet_course
from contacts import contact_keys
from meta_spend import fetch_spend
from leads import read_leads
from google_leads import read_google_leads
from google_spend import read_google_spend
from calendar_calls import read_calls

SID = "1L_6TVhbKtguDhNxyE9GxicpZpc1dvb1Ow7rk-gM3pC4"
EPOCH = dt.date(1899, 12, 30)
SPEND_MULT = 1.22   # +22% sulla spesa di default (es. IVA/markup): spesa trattata come 22% più alta
ACCOUNT = {"Direttore Sportivo": "Calcio", "Istruttore Scuola Calcio": "Calcio",
           "Portieri": "Calcio", "Osservatore": "Calcio", "Match Analyst a 11": "Calcio"}


def parse_date(v):
    if isinstance(v, (int, float)):
        return EPOCH + dt.timedelta(days=int(v)) if 1 <= v <= 100000 else None
    s = str(v).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(s.split()[0], fmt).date()
        except (ValueError, IndexError):
            pass
    return None


def read_closures():
    """Formazione26 A:AU -> chiusure {course, d(iscr), inc(AT), fatt(R/PREZZO), keys}."""
    creds = service_account.Credentials.from_service_account_file(
        "secrets/key.json", scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    svc = gbuild("sheets", "v4", credentials=creds, cache_discovery=False)
    rows = svc.spreadsheets().values().get(
        spreadsheetId=SID, range="Formazione26!A3:AU",
        valueRenderOption="UNFORMATTED_VALUE").execute().get("values", [])
    out, noads = [], []
    for r in rows:
        g = lambda i: r[i] if len(r) > i else None
        num = lambda i: float(g(i)) if isinstance(g(i), (int, float)) else 0.0
        corso = str(g(42) or "").strip()           # AQ = GESTIONE SALDI/Corso
        inc, fatt = num(45), num(17)                # AT = Incassato, R = PREZZO
        if not corso or inc == 0:                    # chiusura = solo se PAGATA (incassato>0)
            continue
        canon = match_sheet_course(corso)
        if canon is None:                           # corso senza ADS (solo incassi)
            noads.append({"course": corso, "d": parse_date(g(41)), "inc": inc, "fatt": fatt})
            continue
        out.append({"course": canon, "d": parse_date(g(41)), "inc": inc, "fatt": fatt,
                    "keys": contact_keys(g(8), g(6), f"{g(1) or ''} {g(2) or ''}")})
    return out, noads


def build_all(span_days=30):
    _, per_day, unattr = fetch_spend(span_days)
    spend_day = defaultdict(float)
    for (_, course, date), s in per_day.items():
        spend_day[(course, dt.date.fromisoformat(date))] += s * SPEND_MULT
    closures, noads = read_closures()
    leads_day, lead_first = read_leads()               # lead Meta (+ contatti)
    gleads_day, gtype, gfirst, gtypeday = read_google_leads()   # lead Google (Calcio) + tipo campagna
    gspend_day, _gun = read_google_spend()                       # spesa Google per (corso,tipo,giorno)
    calls_day, _cun = read_calls(span_days + 5)                   # call fissate da calendario per (corso,giorno)

    dmax = max(d for (_, d) in spend_day)
    dmin = dmax - dt.timedelta(days=span_days - 1)
    inwin = lambda d: d is not None and dmin <= d <= dmax

    courses = sorted(set(c for c, _ in spend_day) | set(x["course"] for x in closures)
                     | set(c for c, _ in leads_day) | set(c for c, _ in gleads_day))
    corsi = []
    for c in courses:
        days = {}
        d = dmin
        while d <= dmax:
            days[d.isoformat()] = {"data": d.isoformat(), "spesa": 0.0, "spesa_google": 0.0, "lead_meta": 0,
                                   "lead_google": 0, "call": 0, "incassato": 0.0, "fatturato": 0.0, "chiusure": 0,
                                   "inc_meta": 0.0, "inc_google": 0.0, "ch_meta": 0, "ch_google": 0}
            d += dt.timedelta(days=1)
        for (cc, dd), v in spend_day.items():
            if cc == c and inwin(dd): days[dd.isoformat()]["spesa"] = round(v, 2)
        for (cc, dd), n in leads_day.items():
            if cc == c and inwin(dd): days[dd.isoformat()]["lead_meta"] = n
        for (cc, dd), n in gleads_day.items():
            if cc == c and inwin(dd): days[dd.isoformat()]["lead_google"] = n
        for (cc, dd), n in calls_day.items():
            if cc == c and inwin(dd): days[dd.isoformat()]["call"] = n
        # lead Google per tipo campagna (Search/PMax/Demand Gen) nelle serie
        for (cc, tp, dd), n in gtypeday.items():
            if cc == c and inwin(dd):
                gc = days[dd.isoformat()].setdefault("gcamp", {}).setdefault(tp, {"lead": 0, "inc": 0.0, "ch": 0, "spesa": 0.0})
                gc["lead"] += n
        # spesa Google (x SPEND_MULT) totale + per tipo campagna
        for (cc, tp, dd), v in gspend_day.items():
            if cc == c and inwin(dd):
                day = days[dd.isoformat()]
                day["spesa_google"] = round(day["spesa_google"] + v * SPEND_MULT, 2)
                gc = day.setdefault("gcamp", {}).setdefault(tp, {"lead": 0, "inc": 0.0, "ch": 0, "spesa": 0.0})
                gc["spesa"] = round(gc["spesa"] + v * SPEND_MULT, 2)
        mfm = lead_first.get(c, {})        # contatti lead Meta
        gfm = gfirst.get(c, {})            # contatti lead Google -> (data, tipo)
        incub = []
        for x in closures:
            if x["course"] != c or not inwin(x["d"]):
                continue
            day = days[x["d"].isoformat()]
            day["incassato"] = round(day["incassato"] + x["inc"], 2)
            day["fatturato"] = round(day["fatturato"] + x["fatt"], 2)
            day["chiusure"] += 1
            # attribuzione piattaforma via match contatto (email/telefono/nome), first-touch
            md = min([mfm[k] for k in x["keys"] if k in mfm], default=None)
            gmatch = [gfm[k] for k in x["keys"] if k in gfm]
            gd = min((m[0] for m in gmatch), default=None)
            gtp = next((m[1] for m in gmatch if m[0] == gd), None) if gd else None
            if md and gd:   plat = "meta" if md <= gd else "google"
            elif md:        plat = "meta"
            elif gd:        plat = "google"
            else:           plat = None    # diretta/organica
            if plat:
                day["inc_" + plat] = round(day["inc_" + plat] + x["inc"], 2)
                day["ch_" + plat] += 1
                ld = md if plat == "meta" else gd
                gg = (x["d"] - ld).days
                if 0 <= gg <= 400: incub.append({"data": x["d"].isoformat(), "gg": gg})
                if plat == "google" and gtp:   # chiusura/incasso al tipo campagna Google
                    gc = day.setdefault("gcamp", {}).setdefault(gtp, {"lead": 0, "inc": 0.0, "ch": 0, "spesa": 0.0})
                    gc["inc"] = round(gc["inc"] + x["inc"], 2); gc["ch"] += 1
        serie = list(days.values())
        if not any(s["spesa"] or s["spesa_google"] or s["lead_meta"] or s["lead_google"] or s["incassato"] for s in serie):
            continue
        corsi.append({"corso": c, "account": ACCOUNT.get(c, "Sportiva"),
                      "google_attivo": c in gtype, "serie": serie, "incub": incub})
    # corsi SENZA ADS (solo incassi/chiusure, nessuna spesa/lead)
    no_tmp = {}
    def noday(course, di):
        return no_tmp.setdefault(course, {}).setdefault(
            di, {"data": di, "incassato": 0.0, "fatturato": 0.0, "chiusure": 0, "call": 0})
    for x in noads:
        if not inwin(x["d"]):
            continue
        e = noday(x["course"], x["d"].isoformat())
        e["incassato"] = round(e["incassato"] + x["inc"], 2)
        e["fatturato"] = round(e["fatturato"] + x["fatt"], 2)
        e["chiusure"] += 1
    adv_names = {c["corso"] for c in corsi}
    for (cc, dd), n in calls_day.items():   # call dei corsi senza ads
        if cc not in adv_names and inwin(dd):
            noday(cc, dd.isoformat())["call"] = n
    def acc_noads(name):
        n = name.lower()
        cal = any(k in n for k in ["calcio", "futsal", "a 5", "a 11", "portieri", "settore giovanile",
                                   "prima squadra", "recupero infortuni", "osservatore", "direttore",
                                   "scuola calcio", "team leader", "agente sportivo", "telecronismo"])
        return "Calcio" if cal else "Sportiva"
    corsi_noads = [{"corso": name, "account": acc_noads(name),
                    "serie": sorted(d.values(), key=lambda s: s["data"])}
                   for name, d in no_tmp.items()]

    return {"aggiornato": dmax.isoformat(), "da": dmin.isoformat(), "a": dmax.isoformat(),
            "corsi": corsi, "corsi_noads": corsi_noads, "spesa_mult": SPEND_MULT,
            "spesa_non_attribuita": round(sum(unattr.values()) * SPEND_MULT, 2)}


if __name__ == "__main__":
    data = build_all(60)   # 60gg: serve storico per il confronto col periodo precedente
    json.dump(data, open("data.json", "w"), ensure_ascii=False, indent=2)
    print(f"Generato data.json — span {data['da']} → {data['a']}, {len(data['corsi'])} corsi")
    for acc in ("Calcio", "Sportiva"):
        cs = [c for c in data["corsi"] if c["account"] == acc]
        sp = sum(s["spesa"] for c in cs for s in c["serie"])
        fa = sum(s["fatturato"] for c in cs for s in c["serie"])
        inc = sum(s["incassato"] for c in cs for s in c["serie"])
        lm = sum(s["lead_meta"] for c in cs for s in c["serie"])
        lg = sum(s["lead_google"] for c in cs for s in c["serie"])
        ch = sum(s["chiusure"] for c in cs for s in c["serie"])
        print(f"\n=== {acc} === spesa €{sp:.0f} | fatturato €{fa:.0f} | incassato €{inc:.0f}"
              f" | lead {lm}+{lg}(G) | chiusure {ch} | ROAS {inc/sp:.2f}x" if sp else f"\n=== {acc} ===")
