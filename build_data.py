"""Dataset dashboard: spesa Meta + incassi/fatturato + lead Meta&Google, per corso/giorno.
Serie giornaliere su 30gg: il front-end calcola qualsiasi intervallo e i totali per accademia."""
import json, datetime as dt
from collections import defaultdict
from google.oauth2 import service_account
from googleapiclient.discovery import build as gbuild
from courses import match_sheet_course, city_of, presenza_course, _norm
from contacts import contact_keys
from meta_spend import fetch_spend
from leads import read_leads, read_auto_funnel
from meta_leads import fetch_lead_counts
from site_leads import read_site
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
    """Formazione26 A:AU -> deal {course, d(iscr), inc(AO), fatt(R/PREZZO), paid, keys}.
    Fatturato generato = col R (PREZZO, anche firmate non saldate); Incassato effettivo = col AO."""
    creds = service_account.Credentials.from_service_account_file(
        "secrets/key.json", scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    svc = gbuild("sheets", "v4", credentials=creds, cache_discovery=False)
    rows = svc.spreadsheets().values().get(
        spreadsheetId=SID, range="Formazione26!A2:BZ",   # A2 = riga intestazioni
        valueRenderOption="UNFORMATTED_VALUE").execute().get("values", [])
    if not rows:
        return [], []
    # risoluzione colonne PER NOME (robusta a inserimenti/spostamenti di colonne nel foglio)
    idx = {}
    for i, h in enumerate(rows[0]):
        k = _norm(h)
        if k and k not in idx:
            idx[k] = i
    col = lambda name: idx.get(_norm(name))
    c_corso, c_prezzo, c_inc = col("corso"), col("prezzo"), col("incassato")   # "Incassato" 1a occ. = sez. GESTIONE SALDI
    c_data, c_mod = col("data iscrizione"), col("modalita")
    c_mail, c_tel, c_cog, c_nome = col("e mail"), col("cellulare"), col("cognome"), col("nome")
    missing = [n for n, c in [("Corso", c_corso), ("PREZZO", c_prezzo), ("Incassato", c_inc), ("Data iscrizione", c_data)] if c is None]
    if missing:
        raise RuntimeError("Formazione26: colonne non trovate (struttura cambiata?): " + ", ".join(missing))
    out, noads = [], []
    for r in rows[1:]:
        g = lambda i: r[i] if (i is not None and len(r) > i) else None
        num = lambda i: float(g(i)) if isinstance(g(i), (int, float)) else 0.0
        corso = str(g(c_corso) or "").strip()
        fatt, inc = num(c_prezzo), num(c_inc)       # PREZZO = fatturato generato; Incassato = effettivo
        if not corso or (fatt <= 0 and inc <= 0):   # riga vuota / non un deal reale
            continue
        paid = inc > 0                              # firmata-non-pagata se incassato 0
        canon = match_sheet_course(corso)
        if canon in ("Pilates Reformer presenza", "Pilates Matwork presenza"):   # presenza -> spacca per citta (MODALITA')
            city = city_of(g(c_mod)) or city_of(corso)
            canon = presenza_course(city) if city else canon
        if canon is None:                           # corso senza ADS (solo incassi)
            noads.append({"course": corso, "d": parse_date(g(c_data)), "inc": inc, "fatt": fatt, "paid": paid})
            continue
        out.append({"course": canon, "d": parse_date(g(c_data)), "inc": inc, "fatt": fatt, "paid": paid,
                    "keys": contact_keys(g(c_mail), g(c_tel), f"{g(c_cog) or ''} {g(c_nome) or ''}")})
    return out, noads


def build_all(span_days=30):
    _, per_day, unattr = fetch_spend(span_days)
    spend_day = defaultdict(float)
    for (_, course, date), s in per_day.items():
        spend_day[(course, dt.date.fromisoformat(date))] += s * SPEND_MULT
    closures, noads = read_closures()
    leads_day, lead_first = read_leads()               # lead Meta (+ contatti)
    funnel_day = read_auto_funnel()                     # funnel messaggi (tab AUTO): lead_auto/contattati/risposte
    try:
        meta_lead_api = fetch_lead_counts(span_days)   # conteggio lead Meta da API (controllo congruenza foglio)
    except Exception as e:
        print("  (controllo lead Meta saltato:", str(e)[:70], ")"); meta_lead_api = {}
    gleads_day, gtype, gtypeday, gfirst, seo_day, seofirst = read_site()  # Google (per UTM) + SEO/organico (per col CORSO)
    gspend_day, _gun = read_google_spend()                       # spesa Google per (corso,tipo,giorno)
    gspend_courses = {cc for (cc, _t, _d) in gspend_day}
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
                                   "lead_google": 0, "lead_seo": 0, "call": 0, "incassato": 0.0, "fatturato": 0.0, "chiusure": 0,
                                   "inc_meta": 0.0, "inc_google": 0.0, "inc_seo": 0.0, "ch_meta": 0, "ch_google": 0, "ch_seo": 0,
                                   "fatt_meta": 0.0, "fatt_google": 0.0, "fatt_seo": 0.0,
                                   "lead_auto": 0, "risposte": 0}
            d += dt.timedelta(days=1)
        for (cc, dd), v in spend_day.items():
            if cc == c and inwin(dd): days[dd.isoformat()]["spesa"] = round(v, 2)
        for (cc, dd), n in leads_day.items():
            if cc == c and inwin(dd): days[dd.isoformat()]["lead_meta"] = n
        for (cc, dd), n in gleads_day.items():
            if cc == c and inwin(dd): days[dd.isoformat()]["lead_google"] = n
        for (cc, dd), n in seo_day.items():
            if cc == c and inwin(dd): days[dd.isoformat()]["lead_seo"] = n
        for (cc, dd), n in calls_day.items():
            if cc == c and inwin(dd): days[dd.isoformat()]["call"] = n
        for (cc, dd), (na, nc, nr) in funnel_day.items():
            if cc == c and inwin(dd):
                days[dd.isoformat()]["lead_auto"] = na; days[dd.isoformat()]["risposte"] = nr
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
        sfm = seofirst.get(c, {})          # contatti lead SEO/organico -> data
        incub = []
        for x in closures:
            if x["course"] != c or not inwin(x["d"]):
                continue
            day = days[x["d"].isoformat()]
            day["incassato"] = round(day["incassato"] + x["inc"], 2)   # AO (anche parziale)
            day["fatturato"] = round(day["fatturato"] + x["fatt"], 2)  # R (anche firmate non saldate)
            day["chiusure"] += 1                                        # ogni iscrizione = una chiusura (anche firmata non saldata)
            # attribuzione canale via match contatto (email/telefono/nome), first-touch tra Meta/Google/SEO
            md = min([mfm[k] for k in x["keys"] if k in mfm], default=None)
            gmatch = [gfm[k] for k in x["keys"] if k in gfm]
            gd = min((m[0] for m in gmatch), default=None)
            gtp = next((m[1] for m in gmatch if m[0] == gd), None) if gd else None
            sd = min([sfm[k] for k in x["keys"] if k in sfm], default=None)
            opts = {}
            if md: opts["meta"] = md
            if gd: opts["google"] = gd
            if sd: opts["seo"] = sd
            plat = min(opts, key=opts.get) if opts else None     # canale del first-touch
            if plat:
                day["inc_" + plat] = round(day["inc_" + plat] + x["inc"], 2)
                day["fatt_" + plat] = round(day["fatt_" + plat] + x["fatt"], 2)
                day["ch_" + plat] += 1
                gg = (x["d"] - opts[plat]).days
                if 0 <= gg <= 400: incub.append({"data": x["d"].isoformat(), "gg": gg})
                if plat == "google" and gtp:   # chiusura/incasso al tipo campagna Google
                    gc = day.setdefault("gcamp", {}).setdefault(gtp, {"lead": 0, "inc": 0.0, "ch": 0, "spesa": 0.0})
                    gc["inc"] = round(gc["inc"] + x["inc"], 2)
                    gc["ch"] += 1
        serie = list(days.values())
        if not any(s["spesa"] or s["spesa_google"] or s["lead_meta"] or s["lead_google"] or s["incassato"] or s["fatturato"] for s in serie):
            continue
        corsi.append({"corso": c, "account": ACCOUNT.get(c, "Sportiva"),
                      "google_attivo": (c in gtype) or (c in gspend_courses), "serie": serie, "incub": incub,
                      "lc_api": meta_lead_api.get(c, 0),                       # lead Meta da API (verità)
                      "lc_sheet": sum(s["lead_meta"] for s in serie)})         # lead Meta arrivati nel foglio
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


def encrypt_data(data, out="data.enc"):
    """Cifra il dataset con la password della dashboard (AES-256-GCM, chiave da PBKDF2).
    Password: env DASH_PASSWORD (cloud) o secrets/dash_password.txt (locale)."""
    import os, base64
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    pw = os.environ.get("DASH_PASSWORD", "").strip()
    if not pw:
        try:
            pw = open("secrets/dash_password.txt").read().strip()
        except FileNotFoundError:
            pass
    if not pw:
        raise RuntimeError("DASH_PASSWORD mancante: imposta il secret su GitHub o secrets/dash_password.txt")
    import hashlib
    salt = hashlib.sha256(b"AIC-AIS-dashboard-salt-v1").digest()[:16]   # fisso: la chiave salvata nel browser resta valida tra i build giornalieri
    iv = os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=150000).derive(pw.encode())
    ct = AESGCM(key).encrypt(iv, json.dumps(data, ensure_ascii=False).encode(), None)
    b64 = lambda b: base64.b64encode(b).decode()
    json.dump({"salt": b64(salt), "iv": b64(iv), "ct": b64(ct)}, open(out, "w"))
    print(f"Generato {out} (dataset cifrato)")


if __name__ == "__main__":
    data = build_all(60)   # 60gg: serve storico per il confronto col periodo precedente
    json.dump(data, open("data.json", "w"), ensure_ascii=False, indent=2)   # solo locale (gitignored), per debug
    encrypt_data(data)
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
