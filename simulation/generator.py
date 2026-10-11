"""Simulador Doador -> ONG (generator_version 0.2.0). Uso: python -m simulation.generator --seed 20261003 --n-lots 60000 --tag main

Gera (data/simulated/<tag>/): sim_donor, sim_lot, sim_lot_text, sim_ong_latent (OCULTO), sim_ong_declared, sim_fleet, sim_pair_outcome,
run_params.json. Toda linha carrega data_origin=SIMULATED, generator_version, seed, dataset_version, source_parameters.
Municípios e ONGs vêm da camada gold REAL; nada é inventado nelas. Sem Faker; sem pessoas físicas; sem CNPJ/nome fictício.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd

from pipelines.common import BRONZE, DATA, GOLD, get_logger
from pipelines.geo import estimated_travel_hours
from . import entities as E
from . import pairs as PR
from .params import GENERATOR_VERSION, PARAMS_FILE, Params, file_sha256
from .textgen import RESERVED_FAMILY, TRAIN_FAMILIES, build_text

log = get_logger("simulation")
SIM_ROOT = DATA / "simulated"


def stamp(df: pd.DataFrame, seed: int, dataset_version: str, source_parameters: str, origin: str = "SIMULATED") -> pd.DataFrame:
    df["data_origin"] = origin
    df["generator_version"] = GENERATOR_VERSION
    df["seed"] = np.int64(seed)
    df["dataset_version"] = dataset_version
    df["source_parameters"] = source_parameters
    return df


def run(seed: int = 20261003, n_lots: int = 60000, n_donors: int = 8000, scenario: dict | None = None, tag: str = "main", out_root: Path | None = None) -> dict:
    t0 = time.time()
    out = (out_root or SIM_ROOT) / tag
    out.mkdir(parents=True, exist_ok=True)
    ss = np.random.SeedSequence(seed)
    names = ["params", "donors", "lots", "texts", "latent", "declared", "fleet", "pairs", "outcomes", "calib", "oracle"]
    kids = dict(zip(names, ss.spawn(len(names))))
    rng = {k: np.random.default_rng(v) for k, v in kids.items()}
    P = Params(rng["params"], scenario)
    dataset_version = f"{GENERATOR_VERSION}+{P.params_hash()[:8]}+{seed}"
    src_params = f"params_v0.2.0.yaml@sha256:{file_sha256(PARAMS_FILE)[:12]}|scenario={json.dumps(P.scenario, sort_keys=True)}"
    log.info("dataset_version=%s", dataset_version)
    orgs = pd.read_parquet(GOLD / "organizations.parquet").reset_index(drop=True)
    terr = pd.read_parquet(GOLD / "territory.parquet")
    terr = terr.rename(columns={"latitude": "latitude", "longitude": "longitude"})
    ref = json.loads((BRONZE / "rbba_referencia.json").read_text(encoding="utf-8"))
    mensal = np.array([m["recebido"] for m in ref["mensal"]], dtype=float); season = mensal / mensal.mean()  # jan..dez (REAL, RBBA 2025)
    nova_t = {i + 1: c["pct"] for i, c in enumerate(ref["classificacao_nova"])}
    hs_key = "lots.hort_share_alto" if P.scenario["hortifruti"] == "alto" else "lots.hort_share_baixo"
    hort_target = P[hs_key]
    sigma_kg = P["lots.kg_sigma"]
    # ---------------- ONGs (latente/declarado/frota)
    latent, declared, fleet_eff = E.make_ongs(P, rng["latent"], rng["declared"], rng["fleet"], orgs)
    log.info("ONGs simuladas (atributos operacionais): %d  [%.0fs]", len(latent), time.time() - t0)
    # ---------------- doadores e lotes
    donors = E.make_donors(P, rng["donors"], terr, n_donors)
    prods = E.product_table(P)
    w_prod, diag = E.calibrate_mix(P, prods, rng["calib"], nova_t, hort_target, sigma_kg)
    lots = E.make_lots(P, rng["lots"], donors, prods, w_prod, n_lots, season, np.datetime64(P["general.period_start"]), int(P["general.period_days"]), sigma_kg)
    log.info("lotes=%d doadores=%d mix=%s [%.0fs]", len(lots), len(donors), {k: round(v, 3) for k, v in diag["nova_kg_share"].items()}, time.time() - t0)
    # ---------------- textos
    pr = P.raw["texts"]; rt = random.Random(int(kids["texts"].generate_state(1)[0])); nrng = rng["texts"]
    fr = {k: float(nrng.uniform(*pr[k]["range"])) for k in ("frac_validade_ausente", "frac_ambigua", "frac_inconsistente", "frac_vago", "frac_duas_categorias")}
    tp = {k: float(nrng.uniform(*pr[k]["range"])) for k in ("p_temp_mention", "p_allergen_mention", "p_typo")}
    probs = np.array([fr["frac_validade_ausente"], fr["frac_ambigua"], fr["frac_inconsistente"], fr["frac_vago"], fr["frac_duas_categorias"]])
    probs = np.append(probs, 1 - probs.sum())
    flag_names = ["ausente", "ambigua", "inconsistente", "vago", "duas_categorias", None]
    fchoice = nrng.choice(6, size=len(lots), p=probs)
    reserved = nrng.random(len(lots)) < pr["p_family_reserved"]["value"]
    fam_train = nrng.choice(TRAIN_FAMILIES, size=len(lots), p=[0.30, 0.35, 0.35])
    split_u = nrng.random(len(lots))
    ref_dates = pd.to_datetime(lots["created_s"], unit="s").dt.date.to_numpy()
    allergen_p = lots["contem_alergenico"].to_numpy()
    rows = []
    cols = ["categoria", "produto", "perecibilidade", "quantidade", "unidade", "dias_ate_validade", "temperatura_conservacao", "exige_refrigeracao"]
    arr = {c: lots[c].to_numpy() for c in cols}
    for i in range(len(lots)):
        lot = {c: arr[c][i] for c in cols}; lot["ref_date"] = ref_dates[i]; lot["allergen_product"] = bool(allergen_p[i])
        fam = RESERVED_FAMILY if reserved[i] else fam_train[i]
        fl = {flag_names[fchoice[i]]: True} if flag_names[fchoice[i]] else {}
        r = build_text(lot, fam, fl, P.taxonomy, rt, tp)
        r["text_id"] = f"T{i:06d}"; r["lot_id"] = lots["lot_id"].iat[i]; r["reference_date"] = str(ref_dates[i])
        r["intended_flag"] = flag_names[fchoice[i]] or ""
        r["text_split"] = "test_heldout" if fam == RESERVED_FAMILY else ("train" if split_u[i] < 0.64 else "val" if split_u[i] < 0.76 else "test_seen")
        r["noise_ops"] = "|".join(r["noise_ops"]); r["difficulty_flags"] = "|".join(r["difficulty_flags"])
        rows.append(r)
    texts = pd.DataFrame(rows)
    log.info("textos=%d [%.0fs]", len(texts), time.time() - t0)
    # ---------------- candidatas, contexto, desfecho
    pl, po, pdist, prank = PR.build_candidates(P, rng["pairs"], orgs, lots, donors)
    log.info("pares candidatos=%d (lotes com candidata=%d de %d) [%.0fs]", len(pl), len(np.unique(pl)), len(lots), time.time() - t0)
    ctx = PR.build_context(P, orgs, lots, donors, latent, declared, fleet_eff, pl, po, pdist, prank, rng["outcomes"])
    A = ctx.A
    rg = rng["outcomes"]
    coef = {k: float(rg.uniform(*P.raw["outcome"][k]["range"])) for k in ("beta_apt", "beta_cat", "beta_cap", "beta_frio", "beta_banco", "beta_dist")}
    L0 = PR.logit_parts(A, coef)
    base = float(rg.uniform(*P["outcome.accept_base_rate"][P.scenario["aceitacao"]]))
    beta0 = PR.calibrate_beta0(L0, base)
    rp = {"p_sem_resposta": float(rg.uniform(*P.raw["logistics"]["p_sem_resposta"]["range"])), "p_sr_fora": float(rg.uniform(*P.raw["logistics"]["p_sem_resposta_fora_horario"]["range"])),
          "resp_sigma": float(rg.uniform(*P.raw["logistics"]["resp_sigma"]["range"])),
          **{k: float(rg.uniform(*P.raw["outcome"][k]["range"])) for k in ("gamma0", "gamma_dist", "gamma_disp", "gamma_dia", "gamma_hr", "sigma_T", "p_noshow")},
          "cold_rate": float(rg.uniform(*P.raw["outcome"]["cold_fail_rate_per_h"]["range"])), "detour": P["logistics.detour"],
          "max_resp_business_min": P["logistics.max_resp_business_min"], "speed_short": P["logistics.speed_short_kmh"], "speed_long": P["logistics.speed_long_kmh"], "service_min": P["logistics.service_min"]}
    oc = PR.simulate_outcomes(A, coef, rg, L0, beta0, rp)
    log.info("beta0=%.3f taxa de aceite alvo=%.3f obtida=%.3f; target médio=%.3f [%.0fs]", beta0, base, oc["aceitou"].mean(), oc["target"].mean(), time.time() - t0)
    # ---------------- ORÁCULO (conhece latentes e coeficientes): P(target) esperada por Monte Carlo num subconjunto de lotes.
    # Serve só para checar que o simulador NÃO é determinístico (oráculo bem abaixo de 100%). NUNCA é feature.
    sub = rng["oracle"].choice(len(lots), size=min(5000, len(lots)), replace=False)
    msk = np.isin(A["lot"], sub)
    A_sub = {k: (v[msk] if isinstance(v, np.ndarray) and v.shape[:1] == L0.shape else v) for k, v in A.items()}
    reps = 24
    p_or = np.mean([PR.simulate_outcomes(A_sub, coef, rng["oracle"], L0[msk], beta0, rp)["target"] for _ in range(reps)], axis=0)
    oracle = pd.DataFrame({"lot_id": lots["lot_id"].to_numpy()[pl[msk]], "ong_id": orgs["ong_id"].to_numpy()[po[msk]], "p_oracle": p_or.astype("float32"),
                           "aviso": "ORÁCULO: usa atributos LATENTES; apenas para validação do simulador; proibido como feature/regra"})
    # ---------------- tabela de pares (observáveis + desfecho)
    elig, bits, lut = PR.eligibility(A)
    speed = np.where(pdist <= 15, rp["speed_short"], rp["speed_long"])
    tdesl = estimated_travel_hours(pdist, rp["detour"], speed, rp["service_min"])
    dmun = donors["municipio_ibge"].to_numpy()[lots["donor_idx"].to_numpy()][pl]
    ong_mun = orgs["municipio_ibge"].to_numpy()[po]
    pair = pd.DataFrame({
        "lot_id": lots["lot_id"].to_numpy()[pl], "ong_id": orgs["ong_id"].to_numpy()[po], "ong_tipo": orgs["ong_tipo"].to_numpy()[po],
        "dist_km": pdist, "rank_distancia": prank, "mesmo_municipio": (dmun == ong_mun),
        "location_precision_doador": "MUNICIPALITY_CENTROID", "location_precision_ong": orgs["location_precision"].to_numpy()[po],
        "geo_quality_ong": orgs["geo_quality"].to_numpy()[po],
        "tempo_deslocamento_est_h": tdesl,
        "tem_frota": A["has_fleet"], "frota_capacidade_declarada_kg": A["fleet_cap_decl"], "frota_refrigerada_declarada": A["fleet_ref_decl"],
        "capacidade_declarada_max_kg_dia": A["cap_decl_max"], "camara_fria_declarada": A["cam_decl"], "categoria_aceita_declarada": A["acc_decl"],
        "n_categorias_aceitas_declaradas": A["n_acc_decl"], "horario_abertura_declarado_h": A["open_decl"], "horario_fechamento_declarado_h": A["close_decl"],
        "n_dias_funcionamento_declarados": np.array([bin(x).count("1") for x in range(128)])[A["mask_decl"].astype(int)],
        "dia_comum_declarado": (A["mask_decl"] & A["don_mask"]) != 0,
        "elegivel_regra": elig, "motivos_exclusao": pd.Series(bits).map(lut).astype("category"),
        "resposta": pd.Categorical(oc["resposta"]), "coletou": oc["coletou"], "coletou_dentro_validade": oc["coletou_dentro_validade"], "target": oc["target"],
        "lote_registrado_em": pd.to_datetime(A["created_s"], unit="s"), "proposta_em": pd.to_datetime(oc["prop_s"], unit="s"),
        "resposta_em": pd.to_datetime(np.where(oc["resposta"] == "SEM_RESPOSTA", np.datetime64("NaT"), pd.to_datetime(oc["resp_s"], unit="s").to_numpy())),
        "coleta_em": pd.to_datetime(np.where(oc["coletou"], pd.to_datetime(oc["coleta_s"], unit="s").to_numpy(), np.datetime64("NaT"))),
    })
    pair["razao_deslocamento_validade"] = (tdesl / ((A["expiry_s"] - A["created_s"]) / 3600.0)).astype("float32")
    pair["horas_resposta"] = np.where(oc["resposta"] == "SEM_RESPOSTA", np.nan, (oc["resp_s"] - oc["prop_s"]) / 3600.0)
    pair["horas_ate_coleta"] = np.where(oc["coletou"], (oc["coleta_s"] - A["created_s"]) / 3600.0, np.nan)
    for c in pair.columns:
        if pair[c].dtype == np.float64 and c not in ("horas_resposta", "horas_ate_coleta"):
            pair[c] = pair[c].astype("float32")
    # ---------------- gravar (cada tabela estampada)
    lots_out = lots.drop(columns=["created_s", "expiry_s", "donor_idx"]).copy()
    donors_out = donors.drop(columns=["size_kg_mult", "lot_weight"]).copy()
    fleet_out = fleet_eff.drop(columns=["fator_uso_efetivo"]).copy()
    tables = {"sim_donor": donors_out, "sim_lot": lots_out, "sim_lot_text": texts, "sim_ong_latent": latent, "sim_ong_declared": declared,
              "sim_fleet": fleet_out, "sim_pair_outcome": pair, "sim_oracle_check": oracle}
    meta = {}
    for name, df in tables.items():
        df = stamp(df, seed, dataset_version, src_params)
        if name == "sim_lot_text":
            df.to_parquet(out / f"{name}.parquet", index=False)
        else:
            df.to_parquet(out / f"{name}.parquet", index=False)
        meta[name] = int(len(df))
    # lotes sem candidata (R5)
    sem_cand = sorted(set(lots["lot_id"]) - set(pair["lot_id"]))
    run_info = {"generator_version": GENERATOR_VERSION, "seed": seed, "dataset_version": dataset_version, "tag": tag, "n_lots": n_lots, "n_donors": n_donors,
                "scenario": P.scenario, "params": P.dump(), "n_rows": meta, "lots_sem_candidata": len(sem_cand),
                "coef": coef, "beta0": beta0, "accept_base_rate_target": base, "accept_rate_obtained": float(oc["aceitou"].mean()), "run_params": rp,
                "text_fractions_drawn": fr, "text_probs_drawn": tp, "mix_calibration": diag, "seconds": round(time.time() - t0, 1)}
    (out / "run_params.json").write_text(json.dumps(run_info, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    np.savez_compressed(out / "_oracle_inputs.npz", L0=L0.astype("float32"), beta0=np.float64(beta0))  # para o teste do oráculo
    log.info("concluído em %.0fs: %s", time.time() - t0, meta)
    return run_info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261003)
    ap.add_argument("--n-lots", type=int, default=60000)
    ap.add_argument("--n-donors", type=int, default=8000)
    ap.add_argument("--tag", default="main")
    ap.add_argument("--aceitacao", default="media"); ap.add_argument("--hortifruti", default="alto"); ap.add_argument("--declarado", default="base")
    a = ap.parse_args()
    run(a.seed, a.n_lots, a.n_donors, {"aceitacao": a.aceitacao, "hortifruti": a.hortifruti, "declarado": a.declarado}, a.tag)


if __name__ == "__main__":
    main()
