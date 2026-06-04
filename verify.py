"""Doppio check: ricalcola in modo indipendente e confronta con data.json (somma 60gg span)."""
import json, ssl, urllib.parse, urllib.request, certifi, datetime as dt
from collections import defaultdict
from google.oauth2 import service_account
from googleapiclient.discovery import build as gbuild
from courses import match_sheet_course
from google_leads import read_google_leads
from leads import read_leads

D = json.load(open("data.json"))
DA, A = D["da"], D["a"]
MULT = D.get("spesa_mult", 1)
TOKEN = open("secrets/meta_token.txt").read().strip()
CTX = ssl.create_default_context(cafile=certifi.where())
ACCT = {"Calcio": "act_505303364156004", "Sportiva": "act_9179156665539364"}

def sumserie(pred, field):
    return sum(s[field] for c in D["corsi"] if pred(c) for s in c["serie"])

print(f"Periodo verificato: {DA} -> {A}  (spesa dashboard include x{MULT})\n")

# 1) SPESA: totale account Meta (indip. dall'attribuzione ad-level) x MULT  vs  dashboard
print("=== 1) SPESA (Meta livello-account x1.22  vs  dashboard) ===")
tr = json.dumps({"since": DA, "until": A})
for acc, aid in ACCT.items():
    u = f"https://graph.facebook.com/v24.0/{aid}/insights?"+urllib.parse.urlencode(
        {"fields":"spend","time_range":tr,"access_token":TOKEN})
    with urllib.request.urlopen(u, context=CTX) as r:
        raw = float((json.load(r).get("data") or [{}])[0].get("spend", 0) or 0)
    dash = sumserie(lambda c: c["account"]==acc, "spesa")
    exp = raw*MULT
    ok = abs(dash-exp) < max(1, exp*0.01)
    print(f"  {acc:9} Meta grezzo €{raw:,.0f} x{MULT} = €{exp:,.0f}  | dashboard(meta) €{dash:,.0f}  -> {'OK' if ok else 'DIFF (resto = spesa non attribuita)'}")

# 1b) SPESA GOOGLE: totale foglio 'spesa' (finestra) x MULT  vs  dashboard spesa_google
print("\n=== 1b) SPESA GOOGLE (foglio script x1.22  vs  dashboard) ===")
import datetime as _dt
def _gdate(s):
    try: return _dt.date.fromisoformat(str(s)[:10])
    except: return None
from google_spend import SOURCES as GSOURCES
_gsvc = gbuild("sheets","v4",credentials=service_account.Credentials.from_service_account_file(
        "secrets/key.json",scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]),cache_discovery=False)
graw=0.0
for _sid,_tab in GSOURCES:
    grows=_gsvc.spreadsheets().values().get(spreadsheetId=_sid,range=_tab+"!A2:C").execute().get("values",[])
    for r in grows:
        d=_gdate(r[0]) if r else None
        if d and DA<=d.isoformat()<=A and len(r)>2:
            try: graw+=float(str(r[2]).replace(",","."))
            except: pass
gdash=sum(s["spesa_google"] for c in D["corsi"] for s in c["serie"])
gexp=graw*MULT
print(f"  Google foglio €{graw:,.0f} x{MULT} = €{gexp:,.0f}  | dashboard €{gdash:,.0f}  -> {'OK' if abs(gdash-gexp)<max(1,gexp*0.01) else 'DIFF!'}")

# 2) CHIUSURE + INCASSATO: ricalcolo indipendente da Formazione26  vs dashboard
print("\n=== 2) CHIUSURE & INCASSATO (ricalcolo foglio  vs  dashboard) ===")
creds = service_account.Credentials.from_service_account_file("secrets/key.json",
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
svc = gbuild("sheets","v4",credentials=creds,cache_discovery=False)
rows = svc.spreadsheets().values().get(spreadsheetId="1L_6TVhbKtguDhNxyE9GxicpZpc1dvb1Ow7rk-gM3pC4",
        range="Formazione26!A3:AU", valueRenderOption="UNFORMATTED_VALUE").execute().get("values",[])
EPOCH=dt.date(1899,12,30)
def pdate(v):
    if isinstance(v,(int,float)) and 1<=v<=100000: return EPOCH+dt.timedelta(days=int(v))
    return None
inc_ind=defaultdict(float); ch_ind=defaultdict(int)
for r in rows:
    g=lambda i:r[i] if len(r)>i else None
    corso=str(g(42) or "").strip(); inc=g(45) if isinstance(g(45),(int,float)) else 0
    d=pdate(g(41)); canon=match_sheet_course(corso)
    if canon and d and DA<=d.isoformat()<=A and inc:
        inc_ind[canon]+=inc; ch_ind[canon]+=1
dash_inc=sum(s["incassato"] for c in D["corsi"] for s in c["serie"])
dash_ch=sum(s["chiusure"] for c in D["corsi"] for s in c["serie"])
print(f"  Incassato: indip €{sum(inc_ind.values()):,.0f}  | dashboard €{dash_inc:,.0f}  -> {'OK' if abs(sum(inc_ind.values())-dash_inc)<5 else 'DIFF!'}")
print(f"  Chiusure : indip {sum(ch_ind.values())}  | dashboard {dash_ch}  -> {'OK' if sum(ch_ind.values())==dash_ch else 'DIFF!'}")

# 3) LEAD: ricalcolo indipendente vs dashboard
print("\n=== 3) LEAD (ricalcolo  vs  dashboard) ===")
ld,_=read_leads(); gd,_,_,_=read_google_leads()
lm=sum(n for (c,d),n in ld.items() if DA<=d.isoformat()<=A)
lg=sum(n for (c,d),n in gd.items() if DA<=d.isoformat()<=A)
dlm=sum(s["lead_meta"] for c in D["corsi"] for s in c["serie"])
dlg=sum(s["lead_google"] for c in D["corsi"] for s in c["serie"])
print(f"  Lead Meta  : indip {lm}  | dashboard {dlm}  -> {'OK' if lm==dlm else 'DIFF!'}")
print(f"  Lead Google: indip {lg}  | dashboard {dlg}  -> {'OK' if lg==dlg else 'DIFF!'}")
