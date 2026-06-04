"""Conteggio lead Meta (Lead Ads) per corso via insights — per il controllo di congruenza col foglio.
Non scarica i singoli lead (serve token di Pagina con leads_retrieval): solo i NUMERI per corso."""
from collections import defaultdict
from courses import match_course
from meta_spend import get_all, _chunks, _tr, ACCOUNTS

LEAD_ACTIONS = ("onsite_conversion.lead_grouped",)   # lead da modulo istantaneo Meta


def _lead_val(actions):
    for a in (actions or []):
        if a.get("action_type") in LEAD_ACTIONS:
            return int(float(a.get("value", 0) or 0))
    return 0


def fetch_lead_counts(span_days=60):
    """Ritorna {corso_canonico: n_lead_meta_da_API} su span_days (stessa finestra della spesa)."""
    per_course = defaultdict(int)
    for account, acc in ACCOUNTS.items():
        for (s, e) in _chunks(span_days):
            rows = get_all(f"{acc}/insights", {
                "fields": "ad_name,adset_name,actions", "level": "ad",
                "time_range": _tr(s, e), "limit": "1000"})
            for r in rows:
                n = _lead_val(r.get("actions"))
                if not n:
                    continue
                course = match_course(account, r.get("ad_name"), r.get("adset_name"))
                if course is not None:
                    per_course[course] += n
    return dict(per_course)


if __name__ == "__main__":
    lc = fetch_lead_counts(60)
    print("=== LEAD META da API (ultimi 60g) ===")
    for c, n in sorted(lc.items(), key=lambda x: -x[1]):
        print(f"  {c:30} {n:>6}")
