#!/bin/zsh
# Aggiornamento quotidiano dashboard: genera data.enc e lo manda a GitHub (che pubblica da solo).
set -e
cd /Users/danieleconti/Desktop/dashboard-roas
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
echo "=== $(date '+%Y-%m-%d %H:%M:%S') avvio refresh ==="
source .venv/bin/activate
python build_data.py
git pull --rebase --quiet origin main || true
if git diff --quiet -- data.enc; then
  echo "data.enc invariato, niente da pubblicare"
else
  git add data.enc
  git commit --quiet -m "Refresh dati $(date '+%Y-%m-%d')"
  git push --quiet origin main
  echo "pubblicato: il sito si aggiorna in ~2 minuti"
fi
echo "=== fine ==="
