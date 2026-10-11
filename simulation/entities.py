"""Entidades SIMULADAS: doadores, lotes (+ calibração do mix por NOVA/hortifrúti), perfil LATENTE e DECLARADO das ONGs, frota.
Municípios e ONGs vêm SEMPRE de fonte real (gold); só atributos operacionais são simulados."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .params import Params

WEEKDAY_PICK = np.array([1, 1, 1, 1, 1, 0.6, 0.2])


def cats_of(P: Params) -> list[str]:
    return list(P.taxonomy["categories"].keys())


def product_table(P: Params) -> pd.DataFrame:
    rows = []
    for ci, (cat, cv) in enumerate(P.taxonomy["categories"].items()):
        for pd_ in cv["products"]:
            masses = {**cv["unit_mass_kg"], **pd_.get("unit_mass_kg", {})}
            probs = dict(cv["unit_probs"])
            if "units_only" in pd_:
                probs = {u: probs.get(u, 0.1) for u in pd_["units_only"]}
            tot = sum(probs.values())
            probs = {u: v / tot for u, v in probs.items()}
            for u in probs:
                masses.setdefault(u, 1.0)
            rows.append({"categoria": cat, "cat_idx": ci, "produto": pd_["name"], "product_name_origin": pd_["origin"], "nova": pd_["nova"],
                         "allergen": bool(pd_.get("allergen", False)), "unit_probs": probs, "unit_mass": masses})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ doadores
def make_donors(P: Params, rng: np.random.Generator, terr: pd.DataFrame, n: int) -> pd.DataFrame:
    tw = P["donors.type_weights"]; types = list(tw); pw = np.array([tw[t] for t in types]); pw /= pw.sum()
    dtype = rng.choice(types, size=n, p=pw)
    sp = P["donors.size_probs"]
    size = np.array([rng.choice(list(sp[t]), p=np.array(list(sp[t].values())) / sum(sp[t].values())) for t in dtype])
    pop = terr["populacao_2026"].to_numpy(dtype=float)
    e, e2 = P["donors.geo_pop_exponent"], P["donors.geo_pop_exponent_produtor"]
    w_main = pop ** e; w_main /= w_main.sum(); w_prod = pop ** e2; w_prod /= w_prod.sum()
    idx = np.where(dtype == "PRODUTOR_HORTIFRUTI", rng.choice(len(terr), size=n, p=w_prod), rng.choice(len(terr), size=n, p=w_main))
    # janela de retirada
    ndays = np.round(rng.uniform(*P.raw["donors"]["pickup_days_n"]["range"], size=n)).astype(int)
    mask = np.zeros(n, dtype=np.int64)
    for i in range(n):
        d = rng.choice(7, size=ndays[i], replace=False, p=WEEKDAY_PICK / WEEKDAY_PICK.sum())
        mask[i] = sum(1 << int(x) for x in d)
    start = np.round(rng.uniform(*P.raw["donors"]["pickup_start_h"]["range"], size=n) * 2) / 2
    dur = np.round(rng.uniform(*P.raw["donors"]["pickup_dur_h"]["range"], size=n) * 2) / 2
    end = np.minimum(start + dur, 22.0)
    load = (np.round(rng.uniform(*P.raw["donors"]["loading_min"]["range"], size=n) / 5) * 5).astype(int)
    mult = P["donors.size_kg_mult"]; wk = P["donors.lots_weekly_weight"]
    df = pd.DataFrame({
        "donor_id": [f"D{i:05d}" for i in range(n)], "donor_type": dtype, "donor_size": size,
        "municipio_ibge": terr["codigo_ibge"].to_numpy()[idx], "uf": terr["uf"].to_numpy()[idx],
        "lat": terr["latitude"].to_numpy()[idx], "lon": terr["longitude"].to_numpy()[idx],
        "donor_geo_basis": "POPULACAO_PROXY", "location_precision": "MUNICIPALITY_CENTROID",
        "dias_retirada_mask": mask, "janela_retirada_inicio_h": start, "janela_retirada_fim_h": end, "tempo_carga_min": load,
        "size_kg_mult": [mult[s] for s in size], "lot_weight": [wk[s] for s in size]})
    return df


# ------------------------------------------------------------------ calibração do mix (R2 + cenário hortifrúti)
def sample_kg(P: Params, cat_names: np.ndarray, size_mult: np.ndarray, rng: np.random.Generator, sigma: float) -> np.ndarray:
    med = P["lots.kg_median"]
    m = np.array([med[c] for c in cat_names]) * size_mult
    lo, hi = P["lots.kg_bounds"]
    return np.clip(np.exp(np.log(m) + sigma * rng.standard_normal(len(m))), lo, hi)


def type_given_cat(P: Params, cats: list[str]) -> tuple[list[str], np.ndarray]:
    tw = P["donors.type_weights"]; aff = P["donors.affinity"]; types = list(tw)
    M = np.array([[tw[t] * aff[t][c] for t in types] for c in cats])  # (cat, type)
    return types, M / M.sum(axis=1, keepdims=True)


def calibrate_mix(P: Params, prods: pd.DataFrame, rng: np.random.Generator, nova_target: dict[int, float], hort_target: float, sigma: float,
                  n_mc: int = 250_000, iters: int = 25) -> tuple[np.ndarray, dict]:
    """Ajusta pesos de produto para que a participação em kg por grupo NOVA e de hortifrúti/frutas atinja os alvos (REAL: RBBA 2025;
    cenário). Ajuste DOCUMENTADO (calibração a agregado real), não silencioso. Retorna pesos e diagnóstico."""
    cats = cats_of(P); types, ptype = type_given_cat(P, cats)
    sm = P["donors.size_kg_mult"]; sp = P["donors.size_probs"]
    # multiplicador médio de tamanho por categoria
    size_names = list(sm)
    e_mult = np.zeros(len(cats))
    for ci in range(len(cats)):
        e = 0.0
        for ti, t in enumerate(types):
            ps = np.array([sp[t][s] for s in size_names]); ps /= ps.sum()
            e += ptype[ci, ti] * float((ps * np.array([sm[s] for s in size_names])).sum())
        e_mult[ci] = e
    # kg esperado por produto via Monte Carlo (inclui truncamento)
    mean_kg = np.zeros(len(prods))
    for ci, cat in enumerate(cats):
        draws_t = rng.choice(len(types), size=n_mc // 4, p=ptype[ci])
        sizes = np.array([rng.choice(size_names, p=np.array([sp[types[t]][s] for s in size_names]) / sum(sp[types[t]][s] for s in size_names)) for t in draws_t[:20000]])
        mult = np.array([sm[s] for s in sizes])
        kg = sample_kg(P, np.array([cat] * len(mult)), mult, rng, sigma)
        mean_kg[(prods["cat_idx"] == ci).to_numpy()] = kg.mean()
    nova = prods["nova"].to_numpy(); is_hort = prods["categoria"].isin(["HORT_FOLHOSAS", "HORT_RAIZES", "HORT_FRUTOS", "FRUTAS"]).to_numpy()
    w = np.ones(len(prods))
    for _ in range(iters):
        share = w * mean_kg; share /= share.sum()
        for g, t in nova_target.items():
            cur = share[nova == g].sum()
            if cur > 0:
                w[nova == g] *= (t / cur) ** 0.8
        share = w * mean_kg; share /= share.sum()
        g1 = share[nova == 1].sum(); h = share[is_hort].sum(); nh = g1 - h
        if h > 0 and nh > 0:
            w[is_hort] *= (hort_target / h) ** 0.8
            w[(nova == 1) & ~is_hort] *= (max(nova_target[1] - hort_target, 1e-3) / nh) ** 0.8
    share = w * mean_kg; share /= share.sum()
    diag = {"nova_kg_share": {int(g): float(share[nova == g].sum()) for g in nova_target}, "nova_target": {int(k): float(v) for k, v in nova_target.items()},
            "hort_share": float(share[is_hort].sum()), "hort_target": float(hort_target)}
    return w, diag


def make_lots(P: Params, rng: np.random.Generator, donors: pd.DataFrame, prods: pd.DataFrame, w_prod: np.ndarray, n: int, season: np.ndarray,
              start_date: np.datetime64, period_days: int, sigma: float) -> pd.DataFrame:
    cats = cats_of(P); types, ptype = type_given_cat(P, cats)
    # tempo de criação
    days = np.arange(period_days); d0 = start_date.astype("datetime64[D]")
    dates = d0 + days
    months = ((dates.astype("datetime64[M]") - dates.astype("datetime64[Y]").astype("datetime64[M]")).astype(int)) % 12  # 0..11
    wd = ((dates.astype("datetime64[D]").astype(int) + 3) % 7)
    dw = season[months] * np.array(P["lots.weekday_weights"])[wd]; dw = dw / dw.sum()
    day = rng.choice(period_days, size=n, p=dw)
    hw = P["lots.hour_weights"]; hrs = np.array(list(hw.keys())); hp = np.array(list(hw.values()), dtype=float); hp /= hp.sum()
    hour = rng.choice(hrs, size=n, p=hp); minute = rng.integers(0, 60, size=n); sec = rng.integers(0, 60, size=n)
    created_s = (d0.astype("datetime64[D]").astype(np.int64) + day) * 86400 + hour * 3600 + minute * 60 + sec
    order = np.argsort(created_s, kind="stable"); created_s = created_s[order]
    # produto, categoria
    pw = w_prod / w_prod.sum()
    pidx = rng.choice(len(prods), size=n, p=pw)
    cat_idx = prods["cat_idx"].to_numpy()[pidx]
    # doador | tipo | categoria
    tcol = {t: i for i, t in enumerate(types)}
    donor_by_type = {t: np.where(donors["donor_type"].to_numpy() == t)[0] for t in types}
    donor_w = donors["lot_weight"].to_numpy()
    didx = np.zeros(n, dtype=int)
    for ci in range(len(cats)):
        m = np.where(cat_idx == ci)[0]
        if not len(m):
            continue
        t_draw = rng.choice(len(types), size=len(m), p=ptype[ci])
        for ti, t in enumerate(types):
            mm = m[t_draw == ti]
            if len(mm):
                cand = donor_by_type[t]
                p = donor_w[cand] / donor_w[cand].sum()
                didx[mm] = rng.choice(cand, size=len(mm), p=p)
    cat_names = np.array(cats)[cat_idx]
    size_mult = donors["size_kg_mult"].to_numpy()[didx]
    kg = sample_kg(P, cat_names, size_mult, rng, sigma)
    # unidade e quantidade (liga texto <-> quantidade_kg)
    unit = np.empty(n, dtype=object); q = np.zeros(n, dtype=np.int64); kg_final = np.zeros(n)
    prod_names = prods["produto"].to_numpy()
    ups = prods["unit_probs"].to_list(); ums = prods["unit_mass"].to_list()
    u_rand = rng.random(n)
    for i in range(n):
        pi = pidx[i]; names = list(ups[pi])
        pr_u = np.array([ups[pi][u] for u in names]); masses = np.array([ums[pi][u] for u in names])
        uf = kg[i] / masses
        okm = (uf >= 0.5) & (uf <= 400)  # evita quantidades irreais (ex.: 2500 bandejas); premissa de implementação
        if okm.any():
            pr_u = pr_u * okm; cp = np.cumsum(pr_u / pr_u.sum()); j = int(np.searchsorted(cp, u_rand[i]))
        else:
            j = int(np.argmax(masses))
        u = names[min(j, len(names) - 1)]; mass = masses[min(j, len(names) - 1)]
        units = max(1, int(round(kg[i] / mass)))
        if units * mass < 5:
            units = int(np.ceil(5 / mass))
        if units * mass > 5000:
            units = max(1, int(5000 // mass))
        unit[i] = u; q[i] = units; kg_final[i] = units * mass
    # validade, refrigeração, temperatura
    cdef = P.taxonomy["categories"]
    scale = {c: float(rng.uniform(*P.raw["lots"]["validity_scale"]["range"])) for c in cats}
    pfz = P["lots.p_frozen_meat"]
    dias = np.zeros(n, dtype=int); temp = np.empty(n, dtype=object); frio = np.zeros(n, dtype=bool)
    r1, r2, r3 = rng.random(n), rng.random(n), rng.random(n)
    for i in range(n):
        c = cat_names[i]; cv = cdef[c]
        frozen = c == "CARNES_PESCADOS" and r1[i] < pfz
        lo, hi = cv["days_frozen"] if frozen else cv["days"]
        if hi > 2:
            lo, hi = max(int(round(lo * scale[c])), 0 if lo == 0 else 1), max(int(round(hi * scale[c])), 1)
        dias[i] = lo + int(r2[i] * (hi - lo + 1)) if hi >= lo else lo
        need = frozen or (r3[i] < cv["p_refrigeracao"])
        frio[i] = need
        temp[i] = "CONGELADO" if frozen else ("REFRIGERADO" if need else "AMBIENTE")
    created = created_s
    expiry_s = (created // 86400 + dias + 1) * 86400  # válido até o fim do dia de validade
    dd = donors.iloc[didx]
    lots = pd.DataFrame({
        "lot_id": [f"L{i:06d}" for i in range(n)], "donor_id": dd["donor_id"].to_numpy(),
        "created_s": created, "created_at": pd.to_datetime(created, unit="s"),
        "categoria": cat_names, "produto": prod_names[pidx], "product_name_origin": prods["product_name_origin"].to_numpy()[pidx],
        "perecibilidade": [cdef[c]["perecibilidade"] for c in cat_names], "temperatura_conservacao": temp,
        "quantidade": q, "unidade": unit, "quantidade_kg": kg_final, "dias_ate_validade": dias,
        "expiry_s": expiry_s, "horas_ate_validade": (expiry_s - created) / 3600.0, "exige_refrigeracao": frio,
        "janela_retirada_inicio_h": dd["janela_retirada_inicio_h"].to_numpy(), "janela_retirada_fim_h": dd["janela_retirada_fim_h"].to_numpy(),
        "dias_retirada_mask": dd["dias_retirada_mask"].to_numpy(), "tempo_carga_min": dd["tempo_carga_min"].to_numpy(),
        "contem_alergenico": prods["allergen"].to_numpy()[pidx],
        "refeicoes_equiv": kg_final / float(P["general.meal_kg"]),
        "nova_group": prods["nova"].to_numpy()[pidx], "donor_idx": didx})
    return lots


# ------------------------------------------------------------------ ONGs: latente, declarado, frota
def make_ongs(P: Params, rng_lat: np.random.Generator, rng_dec: np.random.Generator, rng_fl: np.random.Generator, orgs: pd.DataFrame
              ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cats = cats_of(P); n = len(orgs)
    tipo = orgs["ong_tipo"].to_numpy(); bank = tipo == "BANCO_ALIMENTOS_RBBA"
    cm, cs = P["ongs.cap_median_kg_dia"], P["ongs.cap_sigma"]
    cap = np.exp(np.log(np.where(bank, cm["BANCO_ALIMENTOS_RBBA"], cm["OSC_ASSISTENCIA"])) + np.where(bank, cs["BANCO_ALIMENTOS_RBBA"], cs["OSC_ASSISTENCIA"]) * rng_lat.standard_normal(n))
    pcf = {k: float(rng_lat.uniform(*v)) for k, v in P["ongs.p_camara_fria"].items()}
    camara = rng_lat.random(n) < np.where(bank, pcf["BANCO_ALIMENTOS_RBBA"], pcf["OSC_ASSISTENCIA"])
    apt = rng_lat.standard_normal(n)
    sig_aff = P["ongs.afinidade_sigma"]
    mu_b, mu_o = P["ongs.afinidade_mu_banco"], P["ongs.afinidade_mu_osc"]
    afin = np.column_stack([np.where(bank, mu_b[c], mu_o[c]) + sig_aff * rng_lat.standard_normal(n) for c in cats])
    u = P["ongs.sigma_u"] * rng_lat.standard_normal(n)
    disp = rng_lat.beta(*P["ongs.disp_beta"], size=n)
    oh = P.raw["ongs"]
    open_h = np.round(rng_lat.uniform(*oh["open_h"]["range"], size=n) * 2) / 2; close_h = np.round(rng_lat.uniform(*oh["close_h"]["range"], size=n) * 2) / 2
    p_sab = float(rng_lat.uniform(*oh["p_sabado"]["range"])); p_dom = float(rng_lat.uniform(*oh["p_domingo"]["range"]))
    mask = 0b0011111 | ((rng_lat.random(n) < p_sab).astype(np.int64) << 5) | ((rng_lat.random(n) < p_dom).astype(np.int64) << 6)
    ev_med = float(rng_lat.uniform(*oh["eventual_vehicle_median_kg"]["range"])); ev_sig = P["ongs.eventual_vehicle_sigma"]
    ev_cap = np.exp(np.log(ev_med) + ev_sig * rng_lat.standard_normal(n)); ev_ref = rng_lat.random(n) < float(rng_lat.uniform(*oh["eventual_vehicle_p_refrig"]["range"]))
    # frota (declarada à plataforma; efetiva = declarada x fator_uso)
    pv = {k: float(rng_fl.uniform(*v)) for k, v in P["fleet.p_has_vehicle"].items()}
    has_v = rng_fl.random(n) < np.where(bank, pv["BANCO_ALIMENTOS_RBBA"], pv["OSC_ASSISTENCIA"])
    vt = P["fleet.vehicle_types"]; tp = P["fleet.type_probs"]; vnames = list(vt)
    vtype = np.empty(n, dtype=object); vcap = np.zeros(n); vref = np.zeros(n, dtype=bool); fator = rng_fl.uniform(*P.raw["fleet"]["fator_uso_efetivo"]["range"], size=n)
    p_ref = {t: float(rng_fl.uniform(*vt[t]["p_refrig"])) for t in vnames}
    for b, key in ((True, "BANCO_ALIMENTOS_RBBA"), (False, "OSC_ASSISTENCIA")):
        idx = np.where(has_v & (bank == b))[0]
        pr = np.array([tp[key][t] for t in vnames]); pr /= pr.sum()
        ch = rng_fl.choice(len(vnames), size=len(idx), p=pr)
        for j, i in enumerate(idx):
            t = vnames[ch[j]]; vtype[i] = t; vcap[i] = rng_fl.uniform(*vt[t]["cap"]); vref[i] = rng_fl.random() < p_ref[t]
    ids = orgs["ong_id"].to_numpy()
    latent = pd.DataFrame({"ong_id": ids, "capacidade_efetiva_kg_dia": cap, "camara_fria_efetiva": camara, "aptidao_alimentar": apt, "efeito_aleatorio_ong": u,
                           "disponibilidade_coleta": disp, "open_h_real": open_h, "close_h_real": close_h, "dias_mask_real": mask,
                           "veiculo_eventual_cap_kg": ev_cap, "veiculo_eventual_refrig": ev_ref, "fator_uso_efetivo": fator})
    for k, c in enumerate(cats):
        latent[f"afin_{c}"] = afin[:, k]
    # ---- declarado (a partir do latente, com ruído)
    D = P.raw["declared"]
    bias, sd = P["declared.cap_bias"], P["declared.cap_sigma"]
    cap_decl = cap * np.exp(bias + sd * rng_dec.standard_normal(n))
    bands = np.array(P["declared.cap_bands_kg"], dtype=float)
    band = np.searchsorted(bands, cap_decl, side="right")  # 0..5
    upper = np.append(bands, 10000.0)[band]
    lower = np.insert(bands, 0, 0.0)[band]
    fp, fn = P["declared.p_frio_fp"], P["declared.p_frio_fn"]
    cam_decl = np.where(camara, rng_dec.random(n) >= fn, rng_dec.random(n) < fp)
    thr, pex, pom = P["declared.aff_accept_threshold"], P["declared.p_cat_extra"], P["declared.p_cat_omit"]
    base = afin >= thr
    acc = np.where(base, rng_dec.random(afin.shape) >= pom, rng_dec.random(afin.shape) < pex)
    shift = P["declared.sched_shift_h"]
    unmet = rng_dec.random(n) < P["declared.p_sched_unmet"]
    open_d = np.round((open_h + rng_dec.uniform(-shift, shift, n) - np.where(unmet, rng_dec.uniform(0.5, 1.5, n), 0)) * 2) / 2
    close_d = np.round((close_h + rng_dec.uniform(-shift, shift, n) + np.where(unmet, rng_dec.uniform(1, 3, n), 0)) * 2) / 2
    mask_d = mask | (unmet.astype(np.int64) << 5)
    declared = pd.DataFrame({"ong_id": ids, "capacidade_declarada_faixa_min_kg_dia": lower, "capacidade_declarada_faixa_max_kg_dia": upper,
                             "camara_fria_declarada": cam_decl, "horario_abertura_declarado_h": open_d, "horario_fechamento_declarado_h": close_d,
                             "dias_funcionamento_declarados_mask": mask_d})
    for k, c in enumerate(cats):
        declared[f"aceita_{c}_declarado"] = acc[:, k]
    fleet = pd.DataFrame({"ong_id": ids, "tem_frota": has_v, "tipo_veiculo": vtype, "capacidade_kg": np.where(has_v, vcap, np.nan), "refrigerado": np.where(has_v, vref, False),
                          "base_municipio_ibge": orgs["municipio_ibge"].to_numpy(), "location_precision": orgs["location_precision"].to_numpy()})
    fleet_effective = fleet.assign(fator_uso_efetivo=fator)
    return latent, declared, fleet_effective
