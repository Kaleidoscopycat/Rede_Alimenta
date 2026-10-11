#!/usr/bin/env bash
# Sobe PostgreSQL local + API + Streamlit, roda o fluxo ponta a ponta e encerra tudo (os processos vivem só durante esta chamada).
set -u
cd "$(dirname "$0")/.."
. "$HOME/.rede_alimenta_env"; . "$HOME/venv/bin/activate"
scripts/pg_local.sh start >/dev/null 2>&1
export API_BASE_URL=http://127.0.0.1:8000
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --log-level warning > "$HOME/uvicorn.log" 2>&1 &
API=$!
python -m streamlit run app/streamlit_app.py --server.headless true --server.port 8501 --server.address 127.0.0.1 --browser.gatherUsageStats false > "$HOME/streamlit.log" 2>&1 &
UI=$!
for i in $(seq 1 60); do curl -sf $API_BASE_URL/ready >/dev/null 2>&1 && break; sleep 2; done
echo "ready: $(curl -s $API_BASE_URL/ready)"
echo "streamlit health: $(curl -s http://127.0.0.1:8501/_stcore/health)"
python -W ignore -m scripts.e2e_flow
echo "exit_e2e=$?"
kill $UI $API 2>/dev/null; sleep 1
scripts/pg_local.sh stop >/dev/null 2>&1
tail -3 "$HOME/uvicorn.log"
