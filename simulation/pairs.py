"""Candidatas (K ONGs mais próximas, até 150 km), regras de elegibilidade sobre o DECLARADO e desfecho ESTOCÁSTICO (spec §5).

O desfecho depende de atributos LATENTES (aptidão, afinidade, capacidade/câmara fria efetivas, efeitos aleatórios) e de ruído logístico
por par: nunca é uma regra determinística sobre variáveis observáveis. Os rótulos são CONTRAFACTUAIS (gerados para todos os pares
candidatos); em produção só se observa o par acionado (limitação declarada)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from pipelines.geo import EARTH_RADIUS_KM, estimated_travel_hours
from .params import Params
from .timeutil import DAY, advance_business, dow, next_open_start


def build_candidates(P: Params, rng: np.random.Generator, orgs: pd.DataFrame, lots: pd.DataFrame, donors: pd.DataFrame
                     ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    K, R, cap = int(P["general.k_candidates"]), float(P["general.radius_km"]), int(P["general.pool_cap"])
    ok = orgs["rankable_by_distance"].to_numpy()
    pos = np.where(ok)[0]  # índices (em orgs) de ONGs ranqueáveis por distância
    coords = np.radians(orgs.loc[ok, ["lat", "lon"]].to_numpy(dtype=float))
    tree = BallTree(coords, metric="haversine")
    is_bank = (orgs["ong_tipo"].to_numpy() == "BANCO_ALIMENTOS_RBBA")[ok]
    dmun = donors["municipio_ibge"].to_numpy()[lots["donor_idx"].to_numpy()]
    dlat = donors["lat"].to_numpy()[lots["donor_idx"].to_numpy()]; dlon = donors["lon"].to_numpy()[lots["donor_idx"].to_numpy()]
    out_lot, out_org, out_dist, out_rank = [], [], [], []
    order = np.argsort(dmun, kind="stable")
    bounds = np.flatnonzero(np.diff(dmun[order])) + 1
    for grp in np.split(order, bounds):
        m = dmun[grp[0]]
        ind, dist = tree.query_radius(np.radians([[dlat[grp[0]], dlon[grp[0]]]]), r=R / EARTH_RADIUS_KM, return_distance=True)
        ind, dist = ind[0], dist[0] * EARTH_RADIUS_KM
        if len(ind) == 0:
            continue
        if len(ind) > cap:  # empates desfeitos por sorteio; documentado em params general.pool_cap
            sel = np.argpartition(dist + rng.random(len(dist)) * 1e-3, cap - 1)[:cap]
            ind, dist = ind[sel], dist[sel]
        bank_in = np.where(is_bank[ind])[0]
        nb = bank_in[np.argmin(dist[bank_in])] if len(bank_in) else -1
        k = min(K, len(ind))
        for s in range(0, len(grp), 1500):
            g = grp[s:s + 1500]
            key = dist[None, :] + rng.random((len(g), len(dist))) * 1e-3
            top = np.argpartition(key, k - 1, axis=1)[:, :k] if k < len(dist) else np.tile(np.arange(len(dist)), (len(g), 1))
            kk = np.take_along_axis(key, top, axis=1)
            o = np.argsort(kk, axis=1); top = np.take_along_axis(top, o, axis=1)
            if nb >= 0:  # >= 1 banco RBBA quando existir dentro do raio
                has = is_bank[ind][top].any(axis=1)
                need = ~has & ~(top == nb).any(axis=1)
                top[need, -1] = nb
                o2 = np.argsort(np.take_along_axis(key, top, axis=1), axis=1); top = np.take_along_axis(top, o2, axis=1)
            for r, li in enumerate(g):
                out_lot.append(np.full(k, li, dtype=np.int32)); out_org.append(pos[ind[top[r]]].astype(np.int32))
                out_dist.append(dist[top[r]].astype(np.float32)); out_rank.append(np.arange(1, k + 1, dtype=np.int16))
    return np.concatenate(out_lot), np.concatenate(out_org), np.concatenate(out_dist), np.concatenate(out_rank)


@dataclass
class PairContext:
    A: dict           # arrays por par
    cats: list[str]


def build_context(P: Params, orgs: pd.DataFrame, lots: pd.DataFrame, donors: pd.DataFrame, latent: pd.DataFrame, declared: pd.DataFrame,
                  fleet: pd.DataFrame, pl: np.ndarray, po: np.ndarray, pdist: np.ndarray, prank: np.ndarray, rng: np.random.Generator) -> PairContext:
    cats = list(P.taxonomy["categories"].keys()); cidx = {c: i for i, c in enumerate(cats)}
    lcat = lots["categoria"].map(cidx).to_numpy()
    afin = latent[[f"afin_{c}" for c in cats]].to_numpy()
    acc = declared[[f"aceita_{c}_declarado" for c in cats]].to_numpy()
    n_lots = len(lots)
    sigma_v = float(rng.uniform(*P.raw["ongs"]["sigma_v"]["range"]))
    v_lot = sigma_v * rng.standard_normal(n_lots)
    delay = rng.uniform(*P["logistics.platform_latency_min"], size=n_lots) * 60
    has_f = fleet["tem_frota"].to_numpy(); fcap = fleet["capacidade_kg"].to_numpy(); fref = fleet["refrigerado"].to_numpy(); fat = latent["fator_uso_efetivo"].to_numpy()
    veh_cap = np.where(has_f, np.nan_to_num(fcap) * fat, latent["veiculo_eventual_cap_kg"].to_numpy())
    veh_ref = np.where(has_f, fref, latent["veiculo_eventual_refrig"].to_numpy())
    L = lambda c: lots[c].to_numpy()[pl]
    don_idx = lots["donor_idx"].to_numpy()
    A = {
        "lot": pl, "org": po, "dist": pdist.astype(float), "rank": prank,
        "created_s": L("created_s"), "expiry_s": L("expiry_s"), "kg": L("quantidade_kg"), "frio": L("exige_refrigeracao"), "dias": L("dias_ate_validade"),
        "cat": lcat[pl], "load_min": L("tempo_carga_min"), "don_mask": L("dias_retirada_mask"),
        "don_open_s": (L("janela_retirada_inicio_h") * 3600).astype(np.int64), "don_close_s": (L("janela_retirada_fim_h") * 3600).astype(np.int64),
        "v": v_lot[pl], "delay_s": delay[pl],
        "apt": latent["aptidao_alimentar"].to_numpy()[po], "afin": afin[po, lcat[pl]], "cap_eff": latent["capacidade_efetiva_kg_dia"].to_numpy()[po],
        "cam_eff": latent["camara_fria_efetiva"].to_numpy()[po], "bank": (orgs["ong_tipo"].to_numpy() == "BANCO_ALIMENTOS_RBBA")[po],
        "u": latent["efeito_aleatorio_ong"].to_numpy()[po], "disp": latent["disponibilidade_coleta"].to_numpy()[po],
        "ong_open_s": (latent["open_h_real"].to_numpy()[po] * 3600).astype(np.int64), "ong_close_s": (latent["close_h_real"].to_numpy()[po] * 3600).astype(np.int64),
        "ong_mask": latent["dias_mask_real"].to_numpy()[po], "veh_cap": veh_cap[po], "veh_ref": veh_ref[po],
        # observáveis DECLARADOS
        "cap_decl_max": declared["capacidade_declarada_faixa_max_kg_dia"].to_numpy()[po], "cam_decl": declared["camara_fria_declarada"].to_numpy()[po],
        "acc_decl": acc[po, lcat[pl]], "n_acc_decl": acc.sum(axis=1)[po],
        "open_decl": declared["horario_abertura_declarado_h"].to_numpy()[po], "close_decl": declared["horario_fechamento_declarado_h"].to_numpy()[po],
        "mask_decl": declared["dias_funcionamento_declarados_mask"].to_numpy()[po],
        "has_fleet": has_f[po], "fleet_cap_decl": np.nan_to_num(fcap)[po], "fleet_ref_decl": np.where(has_f, fref, False)[po],
        "resp_median_min": np.where((orgs["ong_tipo"].to_numpy() == "BANCO_ALIMENTOS_RBBA")[po], float(rng.uniform(*P["logistics.resp_median_min"]["BANCO_ALIMENTOS_RBBA"])),
                                     float(rng.uniform(*P["logistics.resp_median_min"]["OSC_ASSISTENCIA"]))),
    }
    return PairContext(A, cats)


def eligibility(A: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    """Regras eliminatórias EXPLÍCITAS sobre o DECLARADO (nunca sobre latentes)."""
    r_cat = ~A["acc_decl"].astype(bool)
    r_cap = A["kg"] > A["cap_decl_max"]
    r_frio = A["frio"].astype(bool) & ~(A["cam_decl"].astype(bool) | A["fleet_ref_decl"].astype(bool))
    r_dia = (A["mask_decl"] & A["don_mask"]) == 0
    bits = r_cat.astype(np.int8) | (r_cap.astype(np.int8) << 1) | (r_frio.astype(np.int8) << 2) | (r_dia.astype(np.int8) << 3)
    names = ["CATEGORIA_NAO_ACEITA_DECLARADA", "CAPACIDADE_DECLARADA_INSUFICIENTE", "SEM_REFRIGERACAO_DECLARADA", "SEM_DIA_COMUM_DECLARADO"]
    lut = {}
    for b in range(16):
        lut[b] = "|".join(n for i, n in enumerate(names) if b >> i & 1)
    return bits == 0, bits, lut


def logit_parts(A: dict, coef: dict) -> np.ndarray:
    return (coef["beta_apt"] * A["apt"] + coef["beta_cat"] * A["afin"] - coef["beta_cap"] * np.log1p(A["kg"] / A["cap_eff"])
            + coef["beta_frio"] * (A["frio"] & ~A["cam_eff"]) + coef["beta_banco"] * A["bank"] + coef["beta_dist"] * np.log1p(A["dist"]) + A["u"] + A["v"])


def calibrate_beta0(L0: np.ndarray, target: float) -> float:
    lo, hi = -15.0, 15.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if (1 / (1 + np.exp(-(L0 + mid)))).mean() > target:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def simulate_outcomes(A: dict, coef: dict, rng: np.random.Generator, L0: np.ndarray, beta0: float, rp: dict) -> dict:
    n = len(L0)
    logit = L0 + beta0
    eps = rng.logistic(size=n)
    accept = (logit + eps) > 0
    prop_s = A["created_s"] + A["delay_s"].astype(np.int64)
    sod = prop_s % DAY
    open_now = ((A["ong_mask"] >> dow(prop_s)) & 1).astype(bool) & (sod >= A["ong_open_s"]) & (sod <= A["ong_close_s"])
    p_sr = np.clip(rp["p_sem_resposta"] * np.where(A["bank"], 0.8, 1.2) + np.where(open_now, 0.0, rp["p_sr_fora"]), 0, 0.9)
    no_resp = rng.random(n) < p_sr
    t_resp_min = A["resp_median_min"] * np.exp(rp["resp_sigma"] * rng.standard_normal(n))
    late = t_resp_min > rp["max_resp_business_min"]  # cauda extrema = sem resposta (premissa documentada)
    no_resp = no_resp | late
    t_resp_min = np.minimum(t_resp_min, rp["max_resp_business_min"])
    resp_s = advance_business(prop_s, t_resp_min, A["ong_open_s"], A["ong_close_s"], A["ong_mask"])
    aceitou = accept & ~no_resp
    # coleta
    wk = (dow(resp_s) >= 5).astype(float); hr = (resp_s % DAY) / 3600.0 / 24.0
    mu = (rp["gamma0"] + rp["gamma_dist"] * np.log1p(A["dist"] * rp["detour"]) + rp["gamma_disp"] * (1 - A["disp"]) + rp["gamma_dia"] * wk + rp["gamma_hr"] * hr)
    T_h = np.exp(mu + rp["sigma_T"] * rng.standard_normal(n))
    ready = resp_s + (T_h * 3600).astype(np.int64)
    coleta_s = next_open_start(ready, A["don_open_s"], A["don_close_s"], A["don_mask"], min_len_s=A["load_min"] * 60)
    speed = np.where(A["dist"] <= 15, rp["speed_short"], rp["speed_long"])
    travel_h = A["dist"] * rp["detour"] / speed
    feasible_cap = A["kg"] <= A["veh_cap"]
    cold_fail = A["frio"] & ~A["veh_ref"].astype(bool) & (rng.random(n) < 1 - np.exp(-rp["cold_rate"] * travel_h))
    noshow = rng.random(n) < rp["p_noshow"]
    coletou = aceitou & feasible_cap & ~cold_fail & ~noshow
    dentro = coletou & (coleta_s <= A["expiry_s"])
    resposta = np.where(no_resp, "SEM_RESPOSTA", np.where(accept, "ACEITOU", "RECUSOU"))
    return {"resposta": resposta, "aceitou": aceitou, "coletou": coletou, "coletou_dentro_validade": dentro, "target": dentro.astype(np.int8),
            "prop_s": prop_s, "resp_s": resp_s, "coleta_s": coleta_s, "t_resp_min": t_resp_min, "p_accept_true": 1 / (1 + np.exp(-logit)),
            "travel_h_est": travel_h}
