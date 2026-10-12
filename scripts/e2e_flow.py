"""Validação ponta a ponta (HTTP real contra API em execução): doador SIMULADO → rascunho com itens → finalização → match (doador sem ranking) → ONG recusa/aceita → rota de coleta planejada → coleta → eventos/tempos.
Somente registros do simulador (SIMULATED) e ONGs reais de fontes públicas; contas são de DEMONSTRAÇÃO (is_demo). Não usa USER_ENTERED nem dados fictícios.
Uso: API_BASE_URL=http://127.0.0.1:8000 python -m scripts.e2e_flow  → escreve docs/E2E_FASE3P1_RESULTADO.json
Variáveis: E2E_SIM_TAG (padrão main; precisa ser a mesma carga importada no banco), E2E_OUT (arquivo de saída)."""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# Portabilidade: permite `python scripts/x.py` de qualquer pasta, sem PYTHONPATH (a raiz do projeto entra em sys.path uma única vez).
_ROOT = str(_Path(__file__).resolve().parent.parent)
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

import json
import os
import re
# Supressão justificada em security/reports/SUPRESSOES.md (B404)
import subprocess  # nosec B404
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
SIM_TAG = os.environ.get("E2E_SIM_TAG", "main")
OUT = Path(os.environ.get("E2E_OUT", str(ROOT / "docs" / "E2E_FASE3P1_RESULTADO.json")))


def mk_user(*args: str, env_var: str | None = None) -> str:
    """Cria a conta pelo CLI. Com `env_var` (variável JÁ definida, ex.: pelo CI) o token vem do ambiente e NÃO passa pela saída do CLI; devolve o token só para uso interno."""
    cmd = [sys.executable, "-m", "scripts.create_user", *args]
    if env_var and os.environ.get(env_var):
        # Supressão justificada em security/reports/SUPRESSOES.md (B603)
        subprocess.run([*cmd, "--token-env", env_var], cwd=ROOT, capture_output=True, text=True, check=True)  # nosec B603
        return os.environ[env_var]
    # Supressão justificada em security/reports/SUPRESSOES.md (B603)
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout  # nosec B603
    return re.search(r"(rai_[A-Za-z0-9_\-]+)", out).group(1)


def plan_route_step(adm: ApiClient, donation_id: str, donor_ext: str, ext2id: dict, org_id: str, needs_cold: bool = False) -> dict:
    """Roteiriza a doação ACEITA (ADMIN): usa o veículo SIMULADO mais próximo da ONG de destino (só 28,9% das ONGs têm frota) e parte na 1ª janela de retirada do doador num dia em que a ONG também funciona."""
    import datetime as dt
    from math import cos, radians
    from core.settings import TZ
    with session_scope() as s:
        dn = s.get(m.Donor, ext2id[donor_ext][0])
        loc = s.get(m.OrganizationLocation, org_id)
        own = s.scalars(select(m.Vehicle).where(m.Vehicle.organization_id == org_id)).first()
        veh = own if (own is not None and (own.refrigerated or not needs_cold)) else None  # lote que exige refrigeração só vai em veículo refrigerado
        if veh is None:
            vs = [v for v in s.scalars(select(m.Vehicle).where(m.Vehicle.base_lat.is_not(None))).all() if v.refrigerated or not needs_cold]
            veh = min(vs, key=lambda v: ((v.base_lat - loc.lat) ** 2 + ((v.base_lon - loc.lon) * cos(radians(loc.lat))) ** 2))
        vid, vinfo = str(veh.id), {"propria_da_ong": own is not None, "tipo": veh.vehicle_type, "capacidade_kg": veh.capacity_kg, "refrigerado": veh.refrigerated, "data_origin": veh.data_origin}
        prof = s.get(m.OrganizationProfile, org_id)
        mask, start_h = dn.pickup_days_mask & prof.open_days_mask, dn.pickup_start_h  # dia em que doador E ONG funcionam
    now = dt.datetime.now(TZ)
    dep = None
    for k in range(0, 8):
        day = (now + dt.timedelta(days=k)).date()
        if (mask >> day.weekday()) & 1:
            cand = dt.datetime.combine(day, dt.time(0, 0), tzinfo=TZ) + dt.timedelta(hours=float(start_h))
            if cand > now:
                dep = cand
                break
    out = adm.plan_route([donation_id], vid, dep.isoformat() if dep else None)
    got = adm.get_route(out["primary"]["id"])
    p = out["primary"]
    return {"veiculo": vinfo, "partida": dep.isoformat() if dep else None, "status": p["status"], "algoritmo": p["algorithm"], "n_paradas": p["n_stops"], "km_est": p["total_km_est"],
            "minutos_est": p["total_minutes_est"], "nao_atendidos": p["unassigned"], "comparacao_baseline": out["comparison"], "data_origin": p["data_origin"], "rotulo": p["rotulo"],
            "get_confere": got["id"] == p["id"] and len(got["stops"]) == len(p["stops"])}


SCORES = {"ML_SCORE", "BUSINESS_RULE_SCORE", "DISTANCE_SCORE", "FINAL_SCORE"}


PARSER_KEYS = {"fields", "confidence", "confidence_threshold", "threshold_note", "parser_version", "parse_confidence", "categoria_conf", "exige_refrigeracao_conf"}


def has_parser_output(obj) -> bool:
    """AJUSTE B0: saída do parser (fields, confiança, versão) não pode aparecer em resposta de DONOR nem de ORG."""
    if isinstance(obj, dict):
        return bool(PARSER_KEYS & set(obj)) or any(has_parser_output(v) for v in obj.values())
    if isinstance(obj, list):
        return any(has_parser_output(v) for v in obj)
    return False


def has_scores(obj) -> bool:
    if isinstance(obj, dict):
        return bool(SCORES & set(obj)) or "ranking" in obj or any(has_scores(v) for v in obj.values())
    if isinstance(obj, list):
        return any(has_scores(v) for v in obj)
    return False


def main() -> None:
    """Tokens POR PERFIL: E2E_ADMIN_TOKEN, E2E_DONOR_TOKEN e E2E_ORG_TOKEN (opcionais; o CI os gera, mascara e passa; sem eles o script gera tokens novos). Cada perfil só usa o seu."""
    admin_tok = mk_user("--role", "ADMIN", "--label", "e2e-admin-local", env_var="E2E_ADMIN_TOKEN")
    with session_scope() as s:
        dv = s.scalar(select(m.Donor.dataset_version).where(m.Donor.data_origin == "SIMULATED").limit(1))
        ext2id = {r.external_id: (r.id, r.municipio_ibge) for r in s.execute(select(m.Donor.external_id, m.Donor.id, m.Donor.municipio_ibge).where(m.Donor.dataset_version == dv))}
    sim = ROOT / "data" / "simulated" / SIM_TAG
    lots = pd.read_parquet(sim / "sim_lot.parquet", columns=["lot_id", "donor_id"])
    txt = pd.read_parquet(sim / "sim_lot_text.parquet", columns=["lot_id", "texto"]).merge(lots, on="lot_id")
    txt = txt[txt["donor_id"].isin(ext2id)]
    txt["mun"] = txt["donor_id"].map(lambda d: ext2id[d][1])
    pick = txt[txt["mun"] == 3550308]
    cand = (pick if len(pick) else txt).reset_index(drop=True)
    row0 = cand.iloc[0]
    donor_tok = mk_user("--role", "DONOR", "--label", "e2e-conta-doador", "--donor-id", str(ext2id[row0["donor_id"]][0]), "--demo", env_var="E2E_DONOR_TOKEN")
    http = httpx.Client(base_url=BASE, timeout=60)
    adm = ApiClient(BASE, admin_tok, http=http)
    don = ApiClient(BASE, donor_tok, http=http)
    # os textos do simulador carregam validades absolutas do relógio SIMULADO (maioria vencida hoje → bloqueio correto). Usa, do doador escolhido, textos ainda válidos hoje.
    bloqueado, validos = None, []
    for r in cand[cand["donor_id"] == row0["donor_id"]].itertuples(index=False):
        pj = adm.parse(r.texto, donor_id=str(ext2id[row0["donor_id"]][0]))  # saída crua do parser: só ADMIN (AJUSTE B0); o doador recebe 410
        f = pj["fields"]
        dv_ = f["dias_ate_validade"]["value"]
        if dv_ is not None and dv_ < 0 and bloqueado is None:
            bloqueado = {"texto": r.texto, "dias_ate_validade": dv_, "blocked": pj["blocked"]}
        if dv_ is not None and dv_ >= 2 and f["categoria"]["value"] and f["quantidade_kg"]["value"] and f["exige_refrigeracao"]["value"] is not None:
            if all(v["categoria"] != f["categoria"]["value"] for v in validos) and len(validos) < 2:
                validos.append({"texto": r.texto, "lot_id": r.lot_id, "categoria": f["categoria"]["value"], "kg": float(f["quantidade_kg"]["value"]), "dias": int(dv_),
                                "refrig": bool(f["exige_refrigeracao"]["value"])})
    if not validos:
        raise SystemExit("nenhum texto simulado válido hoje na amostra")
    res: dict = {"exemplo_bloqueado_por_validade_vencida": bloqueado, "api": BASE, "lotes_simulados_usados": [{k: v[k] for k in ("lot_id", "texto", "categoria")} for v in validos],
                 "donor_id_simulador": row0["donor_id"]}
    t0 = time.perf_counter()
    res["ready"] = http.get("/ready").json()
    res["me"] = don.me()
    # --- rascunho com itens vindos de REGISTROS do simulador (SIMULATED): categoria/kg/validade/refrigeração extraídos dos textos do simulador e CONFIRMADOS pela conta do doador
    import datetime as dt
    from core.settings import TZ
    today = dt.datetime.now(TZ).date()
    dr = don._req("POST", "/api/v1/donations/drafts", json={})
    for v in validos:
        dr = don._req("POST", f"/api/v1/donations/{dr['id']}/items", json={
            "produto": f"lote simulado {v['lot_id']}", "categoria": v["categoria"], "quantity": 1, "unit": "lote", "unit_weight": v["kg"], "unit_weight_unit": "kg",
            "validade_data": (today + dt.timedelta(days=v["dias"])).isoformat(), "exige_refrigeracao": v["refrig"]})
    res["rascunho"] = {"n_items": len(dr["items"]), "resumo": dr["resumo"], "alertas": dr["alertas"], "status": dr["status"]}
    d = don._req("POST", f"/api/v1/donations/{dr['id']}/finalize")
    res["donation_final"] = {k: d[k] for k in ("id", "status", "block_reason", "categoria", "quantity_kg", "validity_days", "data_origin")}
    res["donation_final"]["is_mixed_batch"] = d["resumo"]["is_mixed_batch"]
    if d["status"] != "READY":
        res["parou"] = "doação não ficou READY (regra de validade/confirmação): comportamento esperado do bloqueio"
        OUT.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
        return
    t1 = time.perf_counter()
    mt = don.create_match(d["id"], 5)
    res["match_latencia_http_ms"] = round((time.perf_counter() - t1) * 1000, 1)
    # --- ADMIN: ranking completo e scores (a ÚNICA visão com eles)
    full = adm._req("GET", f"/api/v1/matches/{mt['id']}/ranking")
    res["match_latency_ms_motor"] = full["latency_ms"]
    res["eligibility"] = {k: full["eligibility"][k] for k in ("n_in_radius", "n_eligible", "por_regra")}
    res["alertas_motor"] = full["eligibility"].get("alertas", [])
    res["ranking_top3_ADMIN"] = [{k: c[k] for k in ("posicao", "ong_id", "uf", "dist_km", "location_precision", "distancia_aproximada", "ML_SCORE", "BUSINESS_RULE_SCORE", "DISTANCE_SCORE", "FINAL_SCORE")}
                                 for c in full["ranking"][:3]]
    org_cli, org_tok = {}, {}
    for i, c in enumerate(full["ranking"][:2], start=1):
        tok = mk_user("--role", "ORG", "--label", f"e2e-conta-ong-{i}", "--org-id", c["org_id"], "--demo", env_var="E2E_ORG_TOKEN" if i == 1 else None)
        org_cli[i], org_tok[i] = ApiClient(BASE, tok, http=http), tok
    o1, o2 = org_cli[1], org_cli[2]
    pend = o1.list_matches("PROPOSED")
    res["polling_ong1_pendente"] = [x["id"] for x in pend][:1] == [mt["id"]]
    # --- verificação de visibilidade por perfil, sobre as respostas reais
    ov = o1.get_match(mt["id"])
    res["visibilidade"] = {
        "doador_recebe_saida_do_parser": has_parser_output(dr) or has_parser_output(d) or has_parser_output(don.get_donation(d["id"])),
        "ong_recebe_saida_do_parser": has_parser_output(ov) or has_parser_output(pend),
        "doador_em_parse_antigo": http.post("/api/v1/donations/parse", headers={"Authorization": f"Bearer {donor_tok}"}, json={"texto": validos[0]["texto"]}).status_code,
        "doador_recebe_scores_ou_ranking": has_scores(mt) or has_scores(don.get_match(mt["id"])),
        "ong_recebe_scores_ou_ranking": has_scores(ov) or has_scores(pend),
        "ong_analise_ia_sem_scores": ov["donation"]["analise"],
        "doador_em_predictions": http.post("/api/v1/predictions", headers={"Authorization": f"Bearer {donor_tok}"}, json={}).status_code,
        "doador_em_ranking": http.get(f"/api/v1/matches/{mt['id']}/ranking", headers={"Authorization": f"Bearer {donor_tok}"}).status_code,
        "ong_em_model_info": http.get("/api/v1/model/info", headers={"Authorization": f"Bearer {org_tok[1]}"}).status_code,
        "ong_em_ranking": http.get(f"/api/v1/matches/{mt['id']}/ranking", headers={"Authorization": f"Bearer {org_tok[1]}"}).status_code}
    if res["visibilidade"]["doador_recebe_saida_do_parser"] or res["visibilidade"]["ong_recebe_saida_do_parser"] or res["visibilidade"]["doador_em_parse_antigo"] != 410:
        raise SystemExit("FALHA: saída do parser (fields/confiança) exposta ao doador ou à ONG")
    if res["visibilidade"]["doador_recebe_scores_ou_ranking"] or res["visibilidade"]["ong_recebe_scores_ou_ranking"]:
        raise SystemExit("FALHA: vazamento de scores/ranking para doador ou ONG")
    if res["visibilidade"]["doador_em_ranking"] != 403 or res["visibilidade"]["ong_em_ranking"] != 403 or res["visibilidade"]["doador_em_predictions"] != 403:
        raise SystemExit("FALHA: rotas exclusivas do ADMIN acessíveis a outro perfil")
    o1.respond(mt["id"], False, "sem espaço (e2e)")
    res["apos_recusa"] = {k: don.get_match(mt["id"])[k] for k in ("status", "situacao")}
    o2.respond(mt["id"], True)
    res["rota"] = plan_route_step(adm, d["id"], row0["donor_id"], ext2id, full["ranking"][1]["org_id"], bool(d["exige_refrigeracao"]))
    o2.outcome(mt["id"], "COLLECTED")
    ev = don.events(mt["id"])["events"]
    res["eventos_vistos_pelo_doador"] = [{k: e[k] for k in ("event_type", "to_status", "at", "seconds_since_previous", "actor_type", "data_origin")} for e in ev]
    res["status_final"] = don.get_match(mt["id"])["status"]
    res["metricas_tempo"] = adm._req("GET", "/api/v1/metrics/match-times")
    with session_scope() as s:
        res["auditoria_admin_access"] = len(s.scalars(select(m.AuditLog).where(m.AuditLog.action == "admin.access")).all())
    if res["auditoria_admin_access"] < 1:
        raise SystemExit("FALHA: acesso ADMIN não auditado")
    res["segundos_total_fluxo"] = round(time.perf_counter() - t0, 2)
    res["rotulo"] = "Todos os dados do fluxo são SIMULATED (doador/lote/perfis das ONGs) sobre registros públicos reais de ONGs; tempos de resposta das ONGs são de operadores de teste, NÃO de uso real."
    OUT.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("donation_final", "match_latencia_http_ms", "apos_recusa", "status_final", "visibilidade", "auditoria_admin_access", "segundos_total_fluxo", "rota")},
                     indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
