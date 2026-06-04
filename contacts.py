"""Normalizzazione email/telefono/nome per il match lead<->corsista (vedi regola progetto)."""
import re, unicodedata


def norm_name(v):
    """Nome+cognome normalizzato, indipendente dall'ordine. Serve >=2 token (evita falsi positivi)."""
    if not v:
        return None
    s = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode().lower()
    toks = [t for t in re.split(r"[^a-z]+", s) if len(t) >= 2]
    return " ".join(sorted(toks)) if len(toks) >= 2 else None


def norm_email(v):
    if not v:
        return None
    s = str(v).strip().lower()
    return s if "@" in s and "." in s.split("@")[-1] else None


def norm_phone(v):
    """Solo cifre, via prefisso int.le 39/0039 e zero iniziale -> ultime 9-10 cifre."""
    if v is None:
        return None
    digits = re.sub(r"\D", "", str(v))
    if not digits:
        return None
    digits = re.sub(r"^00", "", digits)      # 0039... -> 39...
    if len(digits) > 10 and digits.startswith("39"):
        digits = digits[2:]                  # togli prefisso Italia
    digits = digits.lstrip("0")              # zero iniziale (fissi/format)
    return digits[-10:] if len(digits) >= 9 else None


def contact_keys(email, phone, name=None):
    """Insieme di chiavi di match per un record: email, telefono e/o nome+cognome normalizzati."""
    keys = set()
    e = norm_email(email)
    p = norm_phone(phone)
    n = norm_name(name)
    if e:
        keys.add("e:" + e)
    if p:
        keys.add("p:" + p)
    if n:
        keys.add("n:" + n)
    return keys
