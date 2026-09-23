#!/bin/zsh
# Aggiornamento quotidiano dashboard (copia automatica fuori dalla Scrivania, per launchd).
set -e
cd /Users/danieleconti/dashboard-roas-auto
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
echo "=== $(date '+%Y-%m-%d %H:%M:%S') avvio refresh ==="
git fetch --quiet origin main
git reset --hard --quiet origin/main
source .venv/bin/activate
# timeout di sicurezza: se una chiamata API resta appesa, abortisce invece di bloccarsi per ore
python - <<'PY'
import socket; socket.setdefaulttimeout(120)   # nessuna chiamata di rete puo' appendere oltre 2 min
import build_data, json
data=build_data.build_all(270)
json.dump(data, open("data.json","w"), ensure_ascii=False, indent=2)
build_data.encrypt_data(data)
print("build OK:", data["da"], "->", data["a"])
PY
if git diff --quiet -- data.enc google_spend_archive.csv; then
  echo "data.enc invariato, niente da pubblicare"
else
  git add data.enc google_spend_archive.csv
  git commit --quiet -m "Refresh dati $(date '+%Y-%m-%d')"
  git push --quiet origin main
  echo "pubblicato: il sito si aggiorna in ~2 minuti"
fi
echo "=== fine ==="
