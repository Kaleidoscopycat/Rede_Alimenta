"""Aplica as migrations e carrega os dados no banco em nuvem (Supabase/PostgreSQL) — roda na MÁQUINA DO RESPONSÁVEL (Fase 3 Parte 2 · Etapa B).

  python -m scripts.load_to_cloud --estimate                      # só estima o tamanho e compara com o limite gratuito; não precisa de DATABASE_URL e não toca em banco algum
  python -m scripts.load_to_cloud                                  # sem --confirm-cloud: NADA é carregado (mostra o plano e o host mascarado)
  python -m scripts.load_to_cloud --confirm-cloud [--sim-tag main]  # aplica `alembic upgrade head` e carrega PÚBLICO + SIMULADO

* DATABASE_URL vem SÓ do ambiente do processo (nunca de arquivo versionado) e NUNCA é impressa: mostra-se apenas o host mascarado, o nome do banco e as contagens.
  Fora do Compose/local exige SSL (`?sslmode=require`). Use a string do pooler em MODO SESSÃO (porta 5432) — ver docs/DEPLOY.md.
* Idempotente: ONGs/municípios/fontes e cada versão do simulador só são inseridos se ainda não existirem; repetir o comando não duplica nada.
* Padrão = carregar TUDO (decisão do grupo com o professor: demonstração acadêmica, ver docs/LICENCAS_DEMONSTRACAO.md). `--only/--exclude` (public|simulated) existem só para testes.
* Dados de pessoas físicas não existem na carga. A separação PÚBLICO / SIMULADO / MEDIDO (`data_origin`) é preservada; a carga NÃO cria nenhum registro USER_ENTERED."""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_ROOT = str(_Path(__file__).resolve().parent.parent)
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
FREE_LIMIT_MB = 500  # Supabase, plano gratuito: "500 MB per project" (https://supabase.com/docs/guides/platform/billing-on-supabase)
# Bytes por linha MEDIDOS no PostgreSQL 16 local com a carga `smoke` (tabela + índices; pg_total_relation_size ÷ linhas) em 2026-10-13. É ESTIMATIVA: em tabelas maiores o custo por linha costuma cair.
BYTES_PER_ROW = {"organizations": 401, "organization_locations": 201, "organization_profiles": 331, "vehicles": 351, "donors": 369, "donor_locations": 287, "donations": 631,
                 "donation_items": 278, "municipalities": 178, "public_indicators": 220}
BASE_OVERHEAD_MB = 10.0  # catálogos do PostgreSQL + tabelas pequenas (medido: ~8 MB num banco recém-migrado) com folga
SSL_MSG = "banco remoto sem SSL: acrescente ?sslmode=require à DATABASE_URL"
PAUSED_MSG = "banco em nuvem pausado ou inacessível: retome o projeto no painel do Supabase (Resume project) e tente de novo"
log = logging.getLogger("load_to_cloud")


def mask_host(host: str | None) -> str:
    """aws-0-sa-east-1.pooler.supabase.com → aws***.com (suficiente para conferir, sem expor o endereço)."""
    if not host:
        return "(sem host)"
    if host in ("localhost", "127.0.0.1", "::1"):
        return host
    return f"{host[:3]}***{host[host.rfind('.'):] if '.' in host else ''}"


def redact(text: str, url: str | None) -> str:
    """Remove de uma mensagem de erro qualquer pedaço da URL (usuário, senha, host)."""
    if not url:
        return text
    p = urlsplit(url)
    for piece in {p.username, p.password, p.hostname, url}:
        if piece:
            text = text.replace(piece, "***")
    return re.sub(r"postgres(ql)?(\+\w+)?://\S+", "postgresql://***", text)


def estimate(sim_tag: str) -> dict:
    """Linhas lidas dos arquivos locais (parquet) × bytes por linha medidos. Não toca em banco."""
    import pandas as pd
    gold, sim = ROOT / "data" / "gold", ROOT / "data" / "simulated" / sim_tag
    rows: dict[str, int] = {}
    if (gold / "organizations.parquet").exists():
        n_org = len(pd.read_parquet(gold / "organizations.parquet", columns=["ong_id"]))
        rows.update(organizations=n_org, organization_locations=n_org, organization_profiles=n_org)
        rows["municipalities"] = len(pd.read_parquet(gold / "territory.parquet", columns=["codigo_ibge"])) if (gold / "territory.parquet").exists() else 0
        rows["public_indicators"] = rows["municipalities"] * 5  # até 5 indicadores por município (alguns sem valor): limite superior
    if sim.exists():
        rows["donors"] = rows["donor_locations"] = len(pd.read_parquet(sim / "sim_donor.parquet", columns=["donor_id"]))
        fleet = pd.read_parquet(sim / "sim_fleet.parquet")
        rows["vehicles"] = int(fleet["tem_frota"].sum()) if "tem_frota" in fleet.columns else len(fleet)
        lots = len(pd.read_parquet(sim / "sim_lot.parquet", columns=["lot_id"]))
        rows["donations"] = rows["donation_items"] = lots
    mb = BASE_OVERHEAD_MB + sum(rows.get(t, 0) * b for t, b in BYTES_PER_ROW.items()) / 1e6
    return {"linhas_por_tabela": rows, "tamanho_estimado_mb": round(mb, 1), "limite_plano_gratuito_mb": FREE_LIMIT_MB, "cabe_no_plano_gratuito": mb < FREE_LIMIT_MB * 0.8,
            "folga_mb": round(FREE_LIMIT_MB - mb, 1), "nota": "estimativa a partir de bytes/linha medidos localmente; use a contagem real e o painel do Supabase para conferir. Reserve folga para auditoria, matches e índices."}


def counts_by_origin() -> dict:
    from sqlalchemy import text
    from database.session import get_engine
    q = {"PÚBLICO: organizações": "select count(*) from organizations where data_origin='PUBLIC'", "PÚBLICO: municípios": "select count(*) from municipalities",
         "PÚBLICO: indicadores": "select count(*) from public_indicators", "PÚBLICO: fontes": "select count(*) from public_data_sources",
         "SIMULADO: perfis de ONG": "select count(*) from organization_profiles where data_origin='SIMULATED'", "SIMULADO: veículos": "select count(*) from vehicles where data_origin='SIMULATED'",
         "SIMULADO: doadores": "select count(*) from donors where data_origin='SIMULATED'", "SIMULADO: doações": "select count(*) from donations where data_origin='SIMULATED'",
         "MEDIDO (USER_ENTERED): doadores": "select count(*) from donors where data_origin='USER_ENTERED'", "MEDIDO (USER_ENTERED): doações": "select count(*) from donations where data_origin='USER_ENTERED'"}
    with get_engine().connect() as c:
        return {k: int(c.execute(text(v)).scalar()) for k, v in q.items()}


def run(args: argparse.Namespace) -> int:
    est = estimate(args.sim_tag)
    print(json.dumps({"estimativa": est}, ensure_ascii=False, indent=2))
    if args.estimate:
        return 0
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL não está definida no ambiente deste processo (veja docs/DEPLOY.md, passo 3). Nada foi feito.")
        return 2
    p = urlsplit(url)
    if not (p.scheme or "").startswith("postgres"):
        print("DATABASE_URL não parece uma URL PostgreSQL. Nada foi feito.")
        return 2
    from core.settings import exigir_ssl_se_remoto
    try:
        os.environ["APP_ENV"] = os.environ.get("APP_ENV", "development")
        exigir_ssl_se_remoto(url)
    except RuntimeError:
        print(SSL_MSG)
        return 2
    destino = f"host={mask_host(p.hostname)} porta={p.port or 5432} banco={(p.path or '/').lstrip('/') or '(padrão)'}"
    if not args.confirm_cloud:
        print(f"PLANO (nada foi carregado): aplicaria migrations e carregaria {args.only or 'public + simulated'} (tag {args.sim_tag}) em {destino}.\nRepita com --confirm-cloud para executar.")
        return 0
    if not est["cabe_no_plano_gratuito"]:
        print("A estimativa passa de 80% do limite do plano gratuito; carga recusada. Reduza a carga (--sim-tag menor) ou use um plano maior.")
        return 3
    print(f"Destino: {destino}")
    from sqlalchemy import text
    from database.session import get_engine, session_scope
    try:
        with get_engine().connect() as c:
            c.execute(text("select 1"))
    except Exception:
        print(PAUSED_MSG)
        return 4
    t0 = time.time()
    try:
        from alembic import command
        from alembic.config import Config
        os.chdir(ROOT)
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        print("Migrations aplicadas (alembic upgrade head).")
        antes = counts_by_origin()
        from database import importers as imp
        rep: dict = {}
        with session_scope() as s:
            if args.only != "simulated" and args.exclude != "public":
                rep["sources"] = imp.import_public_sources(s)
                rep["territory"] = imp.import_municipalities(s)
                rep["food_categories"] = imp.import_food_categories(s)
                rep["organizations"] = imp.import_organizations(s)
                s.commit()
            if args.only != "public" and args.exclude != "simulated":
                rep["simulated"] = imp.import_simulated(s, args.sim_tag, True)
                s.commit()
        depois = counts_by_origin()
        with get_engine().connect() as c:
            tamanho = round(c.execute(text("select pg_database_size(current_database())")).scalar() / 1e6, 1)
    except Exception as e:
        print(f"A carga falhou ({type(e).__name__}): {redact(str(e), url)[:300]}\nVeja 'O que fazer se der erro' em docs/DEPLOY.md.")
        return 1
    log.info("carga em nuvem concluída", extra={"evt": "cloud.load", "contagens": depois, "sim_tag": args.sim_tag, "segundos": round(time.time() - t0, 1)})
    print(json.dumps({"contagens_antes": antes, "contagens_depois": depois, "inseridas_nesta_execucao": rep, "tamanho_do_banco_mb": tamanho, "limite_mb": FREE_LIMIT_MB,
                      "segundos": round(time.time() - t0, 1), "idempotente": "repetir o comando não duplica registros"}, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--confirm-cloud", action="store_true", help="confirma que você quer ESCREVER no banco apontado por DATABASE_URL")
    ap.add_argument("--estimate", action="store_true", help="só estima o tamanho (não usa banco)")
    ap.add_argument("--sim-tag", default="main", help="carga do simulador em data/simulated/<tag> (padrão: main)")
    ap.add_argument("--only", choices=["public", "simulated"], help="(testes) carrega só uma origem")
    ap.add_argument("--exclude", choices=["public", "simulated"], help="(testes) pula uma origem")
    raise SystemExit(run(ap.parse_args()))


if __name__ == "__main__":
    main()
