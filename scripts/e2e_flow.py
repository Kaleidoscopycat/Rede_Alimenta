"""Validação ponta a ponta (HTTP real contra API em execução): doador SIMULADO → parse → doação → confirmação → match → ONG recusa/aceita → coleta → eventos/tempos.
Somente registros do simulador (SIMULATED) e ONGs reais de fontes públicas; contas são de DEMONSTRAÇÃO (is_demo). Não usa USER_ENTERED nem dados fictícios.
Uso: API_BASE_URL=http://127.0.0.1:8000 python -m scripts.e2e_flow  → escreve docs/E2E_FASE2P1_RESULTADO.json"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pandas as pd
from sqlalchemy import select

from app.api_client import ApiClient
from database import models as m
from database.session import session_scope

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")


def mk_user(*args: str) -> str:
    out = subprocess.run([sys.executable, "-m", "scripts.create_user", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return re.search(r"(rai_[A-Za-z0-9_\-]+)", out).group(1)


def main() -> None:
    admin_tok = mk_user("--role", "ADMIN", "--label", "e2e-admin-local")
    with session_scope() as s:
        dv = s.scalar(select(m.Donor.dataset_version).where(m.Donor.data_origin == "SIMULATED").limit(1))
        ext2id = {r.external_id: (r.id, r.municipio_ibge) for r in s.execute(select(m.Donor.external_id, m.Donor.id, m.Donor.municipio_ibge).where(m.Donor.dataset_version == dv))}
    sim = ROOT / "data" / "simulated" / "main"
    lots = pd.read_parquet(sim / "sim_lot.parquet", columns=["lot_id", "donor_id"])
    txt = pd.read_parquet(sim / "sim_lot_text.parquet", columns=["lot_id", "texto"]).merge(lots, on="lot_id")
    txt = txt[txt["donor_id"].isin(ext2id)]
    txt["mun"] = txt["donor_id"].map(lambda d: ext2id[d][1])
    pick = txt[txt["mun"] == 3550308]
    cand = (pick if len(pick) else txt).reset_index(drop=True)
    row0 = cand.iloc[0]
    donor_tok = mk_user("--role", "DONOR", "--label", "e2e-conta-doador", "--donor-id", str(ext2id[row0["donor_id"]][0]), "--demo")
    http = httpx.Client(base_url=BASE, timeout=60)
    adm = ApiClient(BASE, admin_tok, http=http)
    don = ApiClient(BASE, donor_tok, http=http)
    # os textos do simulador carregam validades absolutas do relógio SIMULADO (maioria vencida hoje → bloqueio correto). Escolhe o 1º texto, deste doador, ainda válido hoje.
    bloqueado = None
    row = None
    for r in cand[cand["donor_id"] == row0["donor_id"]].itertuples(index=False):
        pj = don.parse(r.texto)
        dv_ = pj["fields"]["dias_ate_validade"]["value"]
        if dv_ is not None and dv_ < 0 and bloqueado is None:
            bloqueado = {"texto": r.texto, "dias_ate_validade": dv_, "blocked": pj["blocked"]}
        if dv_ is not None and dv_ >= 2:
            row = pd.Series({"texto": r.texto, "lot_id": r.lot_id, "donor_id": r.donor_id})
            break
    if row is None:  # nenhum texto do doador válido hoje: usa texto do simulador de OUTRO doador com validade relativa
        for r in cand.itertuples(index=False):
            pj = don.parse(r.texto)
            if (pj["fields"]["dias_ate_validade"]["value"] or -1) >= 2:
                row = pd.Series({"texto": r.texto, "lot_id": r.lot_id, "donor_id": r.donor_id})
                break
    assert row is not None, "nenhum texto simulado válido hoje na amostra"
    res: dict = {"exemplo_bloqueado_por_validade_vencida": bloqueado, "api": BASE, "texto_simulado": row["texto"], "lot_id_simulador": row["lot_id"], "donor_id_simulador": row["donor_id"]}
    t0 = time.perf_counter()
    res["ready"] = http.get("/ready").json()
    res["me"] = don.me()
    parse = don.parse(row["texto"])
    res["parse"] = {k: parse[k] for k in ("fields", "validity_source", "needs_human_confirmation", "parser_version", "confidence_threshold", "threshold_note", "training_data_origin")}
    d = don.create_donation({"texto": row["texto"]})
    res["donation_inicial"] = {k: d[k] for k in ("id", "status", "block_reason", "pending_fields", "data_origin")}
    if d["status"] == "PENDING_CONFIRMATION":
        body = {"accept_fields": [k for k in d["pending_fields"] if k != "quantidade_kg"]}
        if "quantidade_kg" in d["pending_fields"]:
            body["quantidade_kg"] = float(parse["fields"]["quantidade_kg"]["value"] or 10)
        d = don.confirm(d["id"], body)
        res["confirmacao_aplicada"] = body
    res["donation_final"] = {k: d[k] for k in ("id", "status", "block_reason", "categoria", "quantity_kg", "validity_days", "data_origin")}
    if d["status"] != "READY":
        res["parou"] = "doação não ficou READY (regra de validade/confirmação): comportamento esperado do bloqueio"
        Path(ROOT / "docs" / "E2E_FASE2P1_RESULTADO.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
        return
    t1 = time.perf_counter()
    mt = don.create_match(d["id"], 5)
    res["match_latencia_http_ms"] = round((time.perf_counter() - t1) * 1000, 1)
    res["match_latency_ms_motor"] = mt["latency_ms"]
    res["eligibility"] = {k: mt["eligibility"][k] for k in ("n_in_radius", "n_eligible", "por_regra")}
    res["ranking_top3"] = [{k: c[k] for k in ("posicao", "ong_id", "uf", "dist_km", "location_precision", "distancia_aproximada", "ML_SCORE", "BUSINESS_RULE_SCORE", "DISTANCE_SCORE", "FINAL_SCORE")} for c in mt["ranking"][:3]]
    res["explicacao_top1"] = mt["ranking"][0]["explicacao"]
    org_toks = {}
    for c in mt["ranking"][:2]:
        org_toks[c["posicao"]] = ApiClient(BASE, mk_user("--role", "ORG", "--label", f"e2e-conta-ong-{c['posicao']}", "--org-id", c["org_id"], "--demo"), http=http)
    o1, o2 = org_toks[1], org_toks[2]
    res["polling_ong1_pendente"] = [x["id"] for x in o1.list_matches("PROPOSED")][:1] == [mt["id"]]
    o1.respond(mt["id"], False, "sem espaço (e2e)")
    res["apos_recusa"] = {k: don.get_match(mt["id"])[k] for k in ("status", "current_org", "current_position")}
    o2.respond(mt["id"], True)
    o2.outcome(mt["id"], "COLLECTED")
    ev = don.events(mt["id"])["events"]
    res["eventos"] = [{k: e[k] for k in ("event_type", "to_status", "ong_id", "rank_position", "at", "seconds_since_previous", "actor_type", "data_origin")} for e in ev]
    res["status_final"] = don.get_match(mt["id"])["status"]
    res["metricas_tempo"] = adm._req("GET", "/api/v1/metrics/match-times")
    res["segundos_total_fluxo"] = round(time.perf_counter() - t0, 2)
    res["rotulo"] = "Todos os dados do fluxo são SIMULATED (doador/lote/perfis das ONGs) sobre registros públicos reais de ONGs; tempos de resposta das ONGs são de operadores de teste, NÃO de uso real."
    Path(ROOT / "docs" / "E2E_FASE2P1_RESULTADO.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("donation_final", "match_latencia_http_ms", "apos_recusa", "status_final", "segundos_total_fluxo")}, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
