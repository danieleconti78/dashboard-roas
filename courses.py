"""Matcher corso da nome inserzione/adset Meta. Per-account, regole specifiche->generiche."""
import re, unicodedata

# (corso_canonico, regex sul nome NORMALIZZATO). Ordine = priorità (prima la più specifica).
RULES = {
    "CALCIO": [
        ("Direttore Sportivo",        r"\b(ds|direttore)\b"),
        ("Istruttore Scuola Calcio",  r"\b(isc|istruttore)\b"),
        ("Portieri",                  r"\bportieri\b"),
        ("Osservatore",               r"\b(oss|osservatore)\b"),
        ("Match Analyst a 11",        r"\bmatch\b"),
    ],
    "SPORTIVA": [
        ("Match Analyst Basket",      r"\bbasket\b"),
        ("Match Analyst Pallavolo",   r"\bvolley\b"),
        ("Mental Coach",              r"\bmental\b"),
        ("Istruttore Running",        r"\brunning\b"),
        ("Pilates Matwork",           r"\b(mat|matwork)\b"),       # 'mat' abbreviato o 'matwork' per esteso
        ("Pilates Reformer",          r"\b(ref|reformer)\b"),      # 'ref' abbreviato o 'reformer' per esteso
    ],
}

PRESENZA_CITIES = ("Prato", "Torino", "Milano")


def presenza_course(city: str):
    return f"Reformer presenza {city}"


def is_second_level(text: str):
    """True se e' un 2° livello (rimonetizzazione di chi ha gia' fatto il 1°), non acquisizione da ads."""
    n = _norm(text)
    return "2 livello" in n or "secondo livello" in n


def city_of(text: str):
    """Estrae la citta in presenza da MODALITA'/corso (es. 'Presenza PRATO' -> 'Prato')."""
    n = _norm(text)
    if "milano" in n or "mlano" in n:
        return "Milano"
    if "torino" in n:
        return "Torino"
    if "prato" in n:
        return "Prato"
    return None


def _norm(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)   # underscore, trattini, pipe -> spazio
    return re.sub(r"\s+", " ", s).strip()


def match_course(account: str, *names: str):
    """Prova ogni nome in ordine (ad_name, poi adset_name). Ritorna corso o None.
    Eccezione SPORTIVA: i corsi in PRESENZA (token citta su ad o adset) hanno priorita' assoluta,
    perche' l'ad puo' chiamarsi solo 'ref_pres' mentre la citta sta nell'adset (Prato_/Torino_/Mlano_)."""
    norms = [_norm(n) for n in names if n]
    if account == "SPORTIVA":
        for n in norms:
            c = city_of(n)
            if c:
                return presenza_course(c)
    rules = RULES.get(account, [])
    for n in norms:
        for course, pat in rules:
            if re.search(pat, n):
                return course
    return None


# --- Mapping nomi corso del FOGLIO (chiusure) -> corso canonico (= chiavi spesa). ---
# Solo corsi PUBBLICIZZATI; gli altri (a 5, prima squadra, settore giovanile, ecc.) -> None.
# Regole su testo normalizzato, ordine specifico->generico. Tuple di (parole_richieste, corso).
SHEET_RULES = [
    (("match", "analyst", "basket"), "Match Analyst Basket"),
    (("match", "analyst", "volley"), "Match Analyst Pallavolo"),
    (("match", "analyst", "a 11"),   "Match Analyst a 11"),
    (("mental",),                    "Mental Coach"),
    (("reformer", "presenza"),       "Pilates Reformer presenza"),  # presenza PRIMA dell'online
    (("matwork", "presenza"),        "Pilates Matwork presenza"),
    (("reformer",),                  "Pilates Reformer"),   # online (+2°liv)
    (("matwork",),                   "Pilates Matwork"),
    (("istruttore", "running"),      "Istruttore Running"), # NB: NON "preparatore running"
    (("direttore", "sportivo"),      "Direttore Sportivo"),
    (("osservatore", "a 11"),        "Osservatore"),
    (("portieri", "a 11"),           "Portieri"),           # esclude "preparatore portieri a 5"
    (("istruttore", "calcio", "a 11"), "Istruttore Scuola Calcio"),
]


def match_sheet_course(name: str):
    """Nome corso dal foglio -> corso canonico pubblicizzato, o None se non pubblicizzato."""
    n = _norm(name)
    if not n:
        return None
    for words, course in SHEET_RULES:
        if all(w in n for w in words):
            return course
    return None


if __name__ == "__main__":
    tests = [
        ("CALCIO", "portieri_img70_card2 - m4 - Copia", "Open | Cost Cap 2,8€"),
        ("CALCIO", "img70_card2 - m3", "portieri"),
        ("CALCIO", "ds_1.6", "Direttore Sportivo"),
        ("CALCIO", "4_c1", "Istruttore Scuola Calcio"),
        ("CALCIO", "Direttore Sportivo IMMC3", ""),
        ("SPORTIVA", "mat__9", "Pilates"),
        ("SPORTIVA", "ref__4", "Pilates"),
        ("SPORTIVA", "match_analyst_basket_3", "Basket_1"),
        ("SPORTIVA", "match_volley_21 - m3", "Volley"),
        ("SPORTIVA", "mental_coach_6 – Copy", "Cost Cap - Open - All - 18+"),
        ("SPORTIVA", "pres_mat_TO_1", "Pilates"),
        ("CALCIO", "boh_generico", "Open | Cost Cap"),
    ]
    for acc, ad, adset in tests:
        print(f"{acc:9} {ad[:38]:38} | {adset[:22]:22} -> {match_course(acc, ad, adset)}")
