"""Validação de realismo do simulador (spec §9): R1-R6, T1-T3, L1-L3, oráculo e monotonicidade.
As diferenças encontradas são REGISTRADAS (status PASSA/NAO_PASSA/REPORTADO); nenhum parâmetro é ajustado em silêncio."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from pipelines.common import BRONZE, DATA, GOLD
from ml.evaluation.metrics import ranking_metrics
from sklearn.metrics import roc_auc_score

RBBA_T_POR_RELATORIO = 411.7  # t/relatório/ano (RBBA 2025: kg_recebidos / relatórios) — REAL (agregado)


def _status(ok: bool) -> str:
    return "PASSA" if ok else "NAO_PASSA"


def _norm_ngrams(s: str, n: int = 3) -> set:
    s = re.sub(r"\d+", "#", s.lower()); w = re.findall(r"[a-zçãõáéíóúâêô#]+", s)
    return {tuple(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def ngram_overlap(eval_texts, train_texts, n: int = 3) -> float:
    tr = set()
    for s in train_texts:
        tr |= _norm_ngrams(s, n)
    vals = []
    for s in eval_texts:
        g = _norm_ngrams(s, n)
        if g:
            vals.append(len(g & tr) / len(g))
    return float(np.mean(vals)) if vals else float("nan")


PRIV_PATTERNS = {"cpf": r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", "cnpj": r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b",
                 "telefone": r"(?:\(?\d{2}\)?\s?)?9?\d{4}-?\d{4}\b", "email": r"[\w.+-]+@[\w-]+\.[\w.-]+", "url": r"https?://"}


def validate(tag: str = "main", root: Path | None = None) -> dict:
    d = (root or DATA / "simulated") / tag
    run = json.loads((d / "run_params.json").read_text(encoding="utf-8"))
    lots = pd.read_parquet(d / "sim_lot.parquet"); donors = pd.read_parquet(d / "sim_donor.parquet"); pairs = pd.read_parquet(d / "sim_pair_outcome.parquet")
    texts = pd.read_parquet(d / "sim_lot_text.parquet"); latent = pd.read_parquet(d / "sim_ong_latent.parquet"); fleet = pd.read_parquet(d / "sim_fleet.parquet")
    oracle = pd.read_parquet(d / "sim_oracle_check.parquet")
    terr = pd.read_parquet(GOLD / "territory.parquet"); orgs = pd.read_parquet(GOLD / "organizations.parquet")
    ref = json.loads((BRONZE / "rbba_referencia.json").read_text(encoding="utf-8"))
    res: dict = {"tag": tag, "dataset_version": run["dataset_version"], "scenario": run["scenario"], "checks": {}}
    C = res["checks"]
    # ---------- R1: kg/ano por banco RBBA-equivalente (fluxo realizado: primeiro par positivo na ordem de distância)
    pos = pairs[pairs.target == 1].sort_values(["lot_id", "rank_distancia"]).drop_duplicates("lot_id")
    pos = pos.merge(lots[["lot_id", "quantidade_kg"]], on="lot_id")
    banks = orgs[orgs.ong_tipo == "BANCO_ALIMENTOS_RBBA"]["ong_id"]
    kg_b = pos[pos.ong_id.isin(banks)].groupby("ong_id")["quantidade_kg"].sum().reindex(banks).fillna(0.0) / 1000.0
    period_years = float(run["params"]["drawn"]["general.period_days"]["value"]) / 365.0
    med = float(kg_b.median() / period_years); med_pos = float(kg_b[kg_b > 0].median() / period_years) if (kg_b > 0).any() else 0.0
    ratio = med / RBBA_T_POR_RELATORIO
    C["R1"] = {"descricao": "t/ano por banco RBBA (mediana de 192 bancos) vs 411,7 t/relatório/ano (RBBA 2025)", "sim_mediana_t_ano_todos_bancos": med, "sim_mediana_t_ano_bancos_com_fluxo": med_pos,
               "referencia_t_ano": RBBA_T_POR_RELATORIO, "razao": ratio, "criterio": "0,5x a 2x", "status": _status(0.5 <= ratio <= 2.0),
               "nota": "O conjunto é uma AMOSTRA de lotes (n_lots), não o fluxo nacional: razão < 0,5 indica sub-escala da amostra, não erro de ordem de grandeza do lote. Registrado sem ajuste.",
               "fracao_implicita_da_referencia": ratio}
    # ---------- R2: mix NOVA
    nova = lots.groupby("nova_group")["quantidade_kg"].sum(); nova = nova / nova.sum()
    tgt = {i + 1: c["pct"] for i, c in enumerate(ref["classificacao_nova"])}
    dev = {int(g): float((nova.get(g, 0) - tgt[g]) * 100) for g in tgt}
    C["R2"] = {"descricao": "mix NOVA em kg vs RBBA 2025", "simulado_pct": {int(g): float(nova.get(g, 0) * 100) for g in tgt}, "referencia_pct": {int(g): float(tgt[g] * 100) for g in tgt},
               "desvio_pp": dev, "criterio": "|desvio| <= 2 p.p.", "status": _status(all(abs(v) <= 2 for v in dev.values())),
               "nota": "Calibração a agregado REAL (documentada em mix_calibration); viés de seleção do RBBA (bancos medem o que receberam); mapeamento produto->NOVA é premissa."}
    # ---------- R3: sazonalidade mensal
    lots["mes"] = pd.to_datetime(lots["created_at"]).dt.month
    sim_m = lots.groupby("mes")["quantidade_kg"].sum().reindex(range(1, 13)); sim_idx = (sim_m / sim_m.mean()).to_numpy()
    mens = np.array([m["recebido"] for m in ref["mensal"]]); ref_idx = mens / mens.mean()
    rho = float(spearmanr(sim_idx, ref_idx).statistic); err = np.abs(sim_idx / ref_idx - 1)
    C["R3"] = {"descricao": "índice mensal de kg (jan..dez) vs RBBA 2025", "spearman": rho, "erro_mensal_max": float(err.max()), "erro_mensal_medio": float(err.mean()),
               "simulado": [float(x) for x in sim_idx], "referencia": [float(x) for x in ref_idx], "criterio": "Spearman >= 0,6 e erro mensal <= 15%",
               "status": _status(rho >= 0.6 and err.max() <= 0.15), "nota": "RBBA = 1 ano e variação pequena (0,91-1,11); a amostra de lotes tem ruído de Poisson/cauda pesada."}
    # ---------- R4: geografia dos doadores
    ld = lots.merge(donors[["donor_id", "uf"]], on="donor_id")
    by_uf = ld.groupby("uf").size(); pop_uf = terr.groupby("uf")["populacao_2026"].sum().reindex(by_uf.index)
    r4 = float(np.corrcoef(by_uf, pop_uf)[0, 1])
    C["R4"] = {"descricao": "nº de lotes por UF vs população por UF", "pearson": r4, "criterio": ">= 0,9", "status": _status(r4 >= 0.9),
               "nota": "População é PROXY da densidade de estabelecimentos (CNPJ pendente): R4 mede coerência interna com o proxy, não realismo da distribuição de doadores."}
    # ---------- R5: cobertura
    dm = donors.merge(terr[["codigo_ibge", "n_osc_assistencia_municipio", "n_banco_rbba_municipio", "populacao_2026"]], left_on="municipio_ibge", right_on="codigo_ibge")
    lots_com_cand = lots["lot_id"].isin(pairs["lot_id"]).mean()
    pop_com_osc = terr.loc[terr.n_osc_assistencia_municipio > 0, "populacao_2026"].sum() / terr["populacao_2026"].sum()
    pop_com_banco = terr.loc[terr.n_banco_rbba_municipio > 0, "populacao_2026"].sum() / terr["populacao_2026"].sum()
    C["R5"] = {"descricao": "cobertura de candidatas", "lotes_com_candidata": float(lots_com_cand), "doadores_em_municipio_com_osc": float((dm.n_osc_assistencia_municipio > 0).mean()),
               "doadores_em_municipio_com_banco_rbba": float((dm.n_banco_rbba_municipio > 0).mean()), "pop_em_municipio_com_osc_ref": float(pop_com_osc),
               "pop_em_municipio_com_banco_ref": float(pop_com_banco), "municipios_com_osc_ref": 4421, "municipios_com_ponto_rbba_ref": 161, "status": "REPORTADO"}
    # ---------- R6: perda sem destino
    lot_pos = pairs.groupby("lot_id")["target"].max().reindex(lots["lot_id"]).fillna(0)
    kg_sem = float(lots.loc[(lot_pos.to_numpy() == 0), "quantidade_kg"].sum() / lots["quantidade_kg"].sum())
    C["R6"] = {"descricao": "kg de lotes sem NENHUM par positivo (sem destino possível dentro da validade) vs perda RBBA", "sim_kg_sem_destino_pct": kg_sem * 100,
               "ref_rbba_perda_pct": 4.85, "ref_mapa_pct_faturamento": 1.8, "status": "REPORTADO",
               "nota": "Não é meta: denominadores diferentes (RBBA = kg perdidos/recebidos pelos bancos; aqui = lotes ofertados sem destino viável). Reportado ao lado."}
    # ---------- T1: frações de casos difíceis
    drawn = run["text_fractions_drawn"]; n = len(texts)
    flag_map = {"frac_validade_ausente": "ausente", "frac_ambigua": "ambigua", "frac_inconsistente": "inconsistente", "frac_vago": "vago", "frac_duas_categorias": "duas_categorias"}
    t1 = {}
    for k, f in flag_map.items():
        obs = float((texts["intended_flag"] == f).mean()); t1[k] = {"sorteada": drawn[k], "gerada": obs, "desvio_pp": (obs - drawn[k]) * 100}
    C["T1"] = {"descricao": "frações de casos difíceis geradas vs sorteadas", "detalhe": t1, "criterio": "|desvio| <= 1 p.p.", "status": _status(all(abs(v["desvio_pp"]) <= 1 for v in t1.values()))}
    # ---------- T2: privacidade
    viol = {k: int(texts["texto"].str.contains(p, regex=True).sum()) for k, p in PRIV_PATTERNS.items()}
    C["T2"] = {"descricao": "padrões de CPF/CNPJ/telefone/e-mail/URL nos textos simulados", "ocorrencias": viol, "criterio": "zero", "status": _status(sum(viol.values()) == 0)}
    # ---------- T3: sobreposição de n-gramas (famílias de treino x reservada)
    tr = texts[texts.template_family_id.isin(["F1", "F2", "F3"]) & (texts.text_split == "train")]["texto"].sample(8000, random_state=1)
    C["T3"] = {"descricao": "sobreposição de trigramas de palavras (números->#) com o texto de treino", "test_seen_F1_F3": ngram_overlap(texts[texts.text_split == "test_seen"]["texto"].head(3000), tr),
               "test_heldout_F4": ngram_overlap(texts[texts.text_split == "test_heldout"]["texto"].head(3000), tr), "status": "REPORTADO"}
    prov = DATA / "manual_labeled" / "PROVISORIO_rascunho_ia.csv"
    if prov.exists():
        pv = pd.read_csv(prov, sep=";")
        C["T3"]["rascunho_ia_provisorio"] = ngram_overlap(pv["texto"], tr)
    # ---------- L1: tempo de deslocamento estimado coerente
    rp = run["run_params"]
    speed = np.where(pairs["dist_km"] <= 15, rp["speed_short"], rp["speed_long"])
    recompute = pairs["dist_km"].to_numpy() * rp["detour"] / speed + rp["service_min"] / 60
    l1 = float(np.abs(recompute - pairs["tempo_deslocamento_est_h"].to_numpy()).max())
    C["L1"] = {"descricao": "tempo estimado = dist*desvio/velocidade + serviço", "erro_abs_max_h": l1, "minimo_h": float(pairs["tempo_deslocamento_est_h"].min()),
               "status": _status(l1 < 1e-3 and pairs["tempo_deslocamento_est_h"].min() >= 0)}
    # ---------- L2: respostas só em horário real da ONG
    pr = pairs[pairs.resposta != "SEM_RESPOSTA"][["ong_id", "resposta_em"]].merge(latent[["ong_id", "open_h_real", "close_h_real", "dias_mask_real"]], on="ong_id")
    t = pd.to_datetime(pr["resposta_em"]); sod = (t.dt.hour * 3600 + t.dt.minute * 60 + t.dt.second) / 3600.0; dw = t.dt.dayofweek
    bad = ~(((pr["dias_mask_real"].to_numpy() >> dw.to_numpy()) & 1).astype(bool) & (sod >= pr["open_h_real"] - 1e-9) & (sod <= pr["close_h_real"] + 1e-9))
    C["L2"] = {"descricao": "respostas fora do horário/dia real de funcionamento da ONG", "violacoes": int(bad.sum()), "de": int(len(pr)), "criterio": "zero", "status": _status(int(bad.sum()) == 0)}
    # ---------- L3: capacidade da frota nos lotes coletados
    col = pairs[pairs.coletou][["lot_id", "ong_id"]].merge(lots[["lot_id", "quantidade_kg"]], on="lot_id").merge(fleet[["ong_id", "tem_frota", "capacidade_kg"]], on="ong_id").merge(
        latent[["ong_id", "fator_uso_efetivo", "veiculo_eventual_cap_kg"]], on="ong_id")
    capeff = np.where(col.tem_frota, col.capacidade_kg.fillna(0) * col.fator_uso_efetivo, col.veiculo_eventual_cap_kg)
    v3 = int((col.quantidade_kg.to_numpy() > capeff + 1e-6).sum())
    C["L3"] = {"descricao": "kg do lote <= capacidade efetiva do veículo nos lotes coletados", "violacoes": v3, "de": int(len(col)), "status": _status(v3 == 0)}
    # ---------- oráculo e monotonicidade
    pj = pairs.merge(oracle[["lot_id", "ong_id", "p_oracle"]], on=["lot_id", "ong_id"])
    rm = ranking_metrics(pj, "p_oracle", ks=(1, 3), boot=0)
    auc = float(roc_auc_score(pj["target"], pj["p_oracle"]))
    C["ORACULO"] = {"descricao": "oráculo (conhece latentes/coeficientes; P esperada por 24 repetições) contra o desfecho realizado", "top1_hit_rate": rm["top1_hit_rate"], "top3_hit_rate": rm["top3_hit_rate"],
                    "mrr": rm["mrr"], "ndcg@3": rm["ndcg@3"], "roc_auc_pares": auc, "n_lotes_avaliaveis": rm["n_lotes_avaliaveis"], "criterio": "bem abaixo de 100% (top-1 < 0,9 e AUC < 0,95)",
                    "status": _status(rm["top1_hit_rate"] < 0.9 and auc < 0.95), "origem_metrica": rm["origem_metrica"]}
    acc = pairs[pairs.resposta == "ACEITOU"]
    bins = pd.cut(acc["dist_km"], [-1, 0.001, 15, 30, 60, 100, 150])
    pc = acc.groupby(bins, observed=True)["coletou_dentro_validade"].mean()
    rho_m = float(spearmanr(np.arange(len(pc)), pc.to_numpy()).statistic)
    C["MONOTONICIDADE"] = {"descricao": "P(coleta dentro da validade | aceitou) por faixa de distância", "por_faixa": {str(k): float(v) for k, v in pc.items()}, "spearman_faixa_vs_P": rho_m,
                           "criterio": "distância maior => P menor (Spearman < 0)", "status": _status(rho_m < 0)}
    # ---------- marginais arquivadas
    res["marginais"] = {"target_medio": float(pairs.target.mean()), "taxa_aceite_intencao": float(run["accept_rate_obtained"]), "taxa_coleta": float(pairs.coletou.mean()),
                        "resposta": pairs["resposta"].value_counts(normalize=True).round(4).to_dict(), "lotes_sem_candidata": run["lots_sem_candidata"],
                        "pct_pares_elegiveis_regra": float(pairs.elegivel_regra.mean()), "target_por_categoria": pairs.merge(lots[["lot_id", "categoria"]], on="lot_id").groupby("categoria")["target"].mean().round(4).to_dict(),
                        "n_pares": int(len(pairs)), "n_lotes": int(len(lots)), "pct_lotes_com_positivo": float(lot_pos.mean())}
    (d / "realism.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    return res


def to_markdown(res: dict) -> str:
    L = [f"### Validação de realismo — {res['tag']} (`{res['dataset_version']}`, cenário {res['scenario']})", "", "| Check | Status | Resumo |", "|---|---|---|"]
    def short(k, v):
        if k == "R1": return f"sim {v['sim_mediana_t_ano_todos_bancos']:.1f} t/ano/banco (mediana de 192) vs ref 411,7 → razão {v['razao']:.3f}"
        if k == "R2": return "desvios (p.p.): " + ", ".join(f"NOVA{g}: {x:+.2f}" for g, x in v["desvio_pp"].items())
        if k == "R3": return f"Spearman {v['spearman']:.2f}; erro mensal máx {v['erro_mensal_max']*100:.1f}%"
        if k == "R4": return f"Pearson {v['pearson']:.3f}"
        if k == "R5": return f"lotes com candidata {v['lotes_com_candidata']*100:.1f}%; doadores em município com banco RBBA {v['doadores_em_municipio_com_banco_rbba']*100:.1f}% (pop. ref {v['pop_em_municipio_com_banco_ref']*100:.1f}%)"
        if k == "R6": return f"{v['sim_kg_sem_destino_pct']:.2f}% do kg sem destino viável (ref. RBBA 4,85%, não é meta)"
        if k == "T1": return "desvios (p.p.): " + ", ".join(f"{a.replace('frac_','')}: {b['desvio_pp']:+.2f}" for a, b in v["detalhe"].items())
        if k == "T2": return f"ocorrências: {v['ocorrencias']}"
        if k == "T3": return f"trigramas em comum com treino: F1–F3 {v['test_seen_F1_F3']:.2f}; F4 reservada {v['test_heldout_F4']:.2f}"
        if k == "L1": return f"erro máx {v['erro_abs_max_h']:.2e} h"
        if k == "L2": return f"{v['violacoes']} violações em {v['de']:,}"
        if k == "L3": return f"{v['violacoes']} violações em {v['de']:,}"
        if k == "ORACULO": return f"top-1 {v['top1_hit_rate']:.3f}; top-3 {v['top3_hit_rate']:.3f}; AUC {v['roc_auc_pares']:.3f}"
        if k == "MONOTONICIDADE": return f"Spearman faixa×P = {v['spearman_faixa_vs_P']:.2f}"
        return ""
    for k, v in res["checks"].items():
        L.append(f"| {k} | {v['status']} | {short(k, v)} |")
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    r = validate(sys.argv[1] if len(sys.argv) > 1 else "main")
    print(to_markdown(r))
