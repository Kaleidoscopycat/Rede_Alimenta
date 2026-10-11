#!/usr/bin/env bash
# PostgreSQL LOCAL avulso (sem Docker) para desenvolvimento da Fase 2 Parte 1.
# Uso: scripts/pg_local.sh init|start|stop|status
# Variáveis: PGDATA_DIR (padrão ~/rede_alimenta_pgdata), PGPORT (5433), PG_BIN (padrão: pg_ctl do PATH ou binários do pacote pip `pgserver`),
#            POSTGRES_PASSWORD (obrigatória no init; NUNCA versionar), APP_DB / APP_USER (padrão rede_alimenta).
# Alternativa com Docker (se disponível na sua máquina):
#   docker run -d --name rede-alimenta-pg -e POSTGRES_PASSWORD=*** -e POSTGRES_DB=rede_alimenta -p 5433:5432 postgres:16
set -euo pipefail
PGDATA_DIR="${PGDATA_DIR:-$HOME/rede_alimenta_pgdata}"
PGPORT="${PGPORT:-5433}"
APP_DB="${APP_DB:-rede_alimenta}"
APP_USER="${APP_USER:-rede_alimenta}"
if [[ -z "${PG_BIN:-}" ]]; then
  if command -v pg_ctl >/dev/null 2>&1; then PG_BIN="$(dirname "$(command -v pg_ctl)")"
  else PG_BIN="$(python3 -c 'import pgserver,pathlib;print(pathlib.Path(pgserver.__file__).parent/"pginstall"/"bin")' 2>/dev/null)"; fi
fi
SOCK_DIR="${PGSOCK_DIR:-/tmp/rede_alimenta_pgsock}"; mkdir -p "$SOCK_DIR"
cmd="${1:-status}"
case "$cmd" in
  init)
    : "${POSTGRES_PASSWORD:?defina POSTGRES_PASSWORD no ambiente}"
    if [[ -f "$PGDATA_DIR/PG_VERSION" ]]; then echo "cluster já existe em $PGDATA_DIR"; exit 0; fi
    pwf="$(mktemp)"; printf '%s' "$POSTGRES_PASSWORD" > "$pwf"
    "$PG_BIN/initdb" -D "$PGDATA_DIR" -U postgres --auth=scram-sha-256 --pwfile="$pwf" -E UTF8 --locale=C.UTF-8 >/dev/null
    rm -f "$pwf"
    "$0" start
    PGPASSWORD="$POSTGRES_PASSWORD" "$PG_BIN/psql" -h 127.0.0.1 -p "$PGPORT" -U postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE $APP_USER LOGIN PASSWORD '$POSTGRES_PASSWORD'" -c "CREATE DATABASE $APP_DB OWNER $APP_USER" -c "CREATE DATABASE ${APP_DB}_test OWNER $APP_USER" >/dev/null
    echo "cluster criado: db=$APP_DB user=$APP_USER porta=$PGPORT";;
  start)
    "$PG_BIN/pg_ctl" -D "$PGDATA_DIR" -o "-p $PGPORT -c listen_addresses=127.0.0.1 -c unix_socket_directories=$SOCK_DIR" -l "$PGDATA_DIR/server.log" -w start >/dev/null && echo "postgres no ar (127.0.0.1:$PGPORT)";;
  stop)  "$PG_BIN/pg_ctl" -D "$PGDATA_DIR" -m fast -w stop >/dev/null && echo "postgres parado";;
  status) "$PG_BIN/pg_ctl" -D "$PGDATA_DIR" status || true; "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" || true;;
  *) echo "uso: $0 init|start|stop|status"; exit 2;;
esac
