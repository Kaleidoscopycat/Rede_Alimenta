#!/usr/bin/env python3
"""Validação programática da Fase 0 (Rede Alimenta IA) — fluxo DOADOR -> ONG.

- Lê SOMENTE data/raw/ (nunca modifica o RAW).
- Lê o cadastro IPEA/OSC COMPLETO em chunks (sem amostragem).
- Executa asserts (testes) e grava:
    docs/data/VALIDATION_LOG.txt          (log legível)
    docs/data/PHASE0_PROFILE.json         (estatísticas reais usadas na spec de simulação)
    data/metadata/raw_checksums.json      (sha256 + tamanho de cada arquivo RAW)
- Não gera nenhum dado simulado.
Uso: python3 scripts/validate_phase0_data.py
"""
from __future__ import annotations
import hashlib, json, math, sys, unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
LOG: list[str] = []
FAILS: list[str] = []
PROFILE: dict = {"generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def log(s: str = "") -> None:
    print(s)
    LOG.append(str(s))


def check(cond: bool, msg: str) -> None:
    log(f"[{'OK' if cond else 'FALHA'}] {msg}")
    if not cond:
        FAILS.append(msg)


def norm(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


log("=" * 70)
log("VALIDAÇÃO PROGRAMÁTICA — FASE 0 (revisada: DOADOR -> ONG)")
log(f"Execução (UTC): {PROFILE['generated_at_utc']}")
log("=" * 70)

# ---------------------------------------------------------------- checksums
log("\n--- 0. Checksums RAW (sha256) ---")
_prev_path = ROOT / "data" / "metadata" / "raw_checksums.json"
prev_checks = json.loads(_prev_path.read_text(encoding="utf-8")) if _prev_path.exists() else None
checks = {}
for p in sorted(RAW.rglob("*")):
    if p.is_file():
        checks[str(p.relative_to(ROOT)).replace("\\", "/")] = {"sha256": sha256(p), "bytes": p.stat().st_size}
(ROOT / "data" / "metadata").mkdir(parents=True, exist_ok=True)
(ROOT / "data" / "metadata" / "raw_checksums.json").write_text(json.dumps(checks, indent=2, ensure_ascii=False), encoding="utf-8")
log(f"{len(checks)} arquivos RAW registrados em data/metadata/raw_checksums.json")
if prev_checks is None:
    log("Sem checksums anteriores para comparar (primeira execução).")
else:
    changed = sorted(k for k in set(checks) | set(prev_checks) if checks.get(k) != prev_checks.get(k))
    check(not changed, f"RAW INALTERADO em relação aos checksums da execução anterior (diferenças: {changed})")

# ---------------------------------------------------------------- IBGE
log("\n--- 1. IBGE: municípios e população ---")
ibge = json.loads((RAW / "ibge/ibge_municipios.json").read_text(encoding="utf-8"))
codes7 = {int(m["id"]) for m in ibge}
check(len(ibge) == 5571 and len(codes7) == 5571, f"IBGE municípios = {len(ibge)} (únicos {len(codes7)})")


def uf_of(m):
    if m.get("microrregiao"):
        return m["microrregiao"]["mesorregiao"]["UF"]["sigla"]
    return m["regiao-imediata"]["regiao-intermediaria"]["UF"]["sigla"]


muni_idx = {(norm(m["nome"]), uf_of(m)): int(m["id"]) for m in ibge}
pop_json = json.loads((RAW / "ibge/ibge_populacao_municipios_2026.json").read_text(encoding="utf-8"))
serie = pop_json[0]["resultados"][0]["series"]
pop = {int(s["localidade"]["id"]): int(s["serie"]["2026"]) for s in serie if s["serie"].get("2026", "").isdigit()}
check(len(pop) == 5571, f"População 2026 com valor numérico para {len(pop)} municípios")
check(sum(pop.values()) == 214_211_951, f"Soma da população = {sum(pop.values()):,}")

# ---------------------------------------------------------------- coordenadas
log("\n--- 2. Coordenadas de município (compilação de terceiros; ver DATA_SOURCE_CANDIDATES) ---")
cent = pd.read_csv(RAW / "ibge_coords/kelvins_municipios.csv").set_index("codigo_ibge")
check(set(cent.index) == codes7, "Centroides cobrem exatamente os 5.571 códigos IBGE (interseção total)")
check(cent.latitude.between(-34, 6).all() and cent.longitude.between(-74, -32).all(), "Todas as coordenadas dentro do retângulo do Brasil")
PROFILE["centroides"] = {"n": int(len(cent)), "fonte": "kelvins/municipios-brasileiros (MIT) — compilação de terceiros; origem primária não declarada"}

# ---------------------------------------------------------------- RBBA
log("\n--- 3. RBBA ---")
rbba = json.loads((RAW / "rbba/rbba_resumo.json").read_text(encoding="utf-8"))
feats = rbba["pontos"]["features"]
check(len(feats) == 192, f"RBBA pontos georreferenciados = {len(feats)}")
ids = [f["properties"]["identificador"] for f in feats]
check(len(set(ids)) == len(ids), "Identificadores RBBA únicos")
dists, anomalias, nao_casados = [], [], []
for f in feats:
    q = f["properties"]
    lon, lat = f["geometry"]["coordinates"]
    c = muni_idx.get((norm(q["cidade"]), q["uf"]))
    if c is None:
        nao_casados.append(q["identificador"])
        continue
    d = haversine_km(lat, lon, cent.loc[c, "latitude"], cent.loc[c, "longitude"])
    dists.append(d)
    if d > 100:
        anomalias.append({"id": q["identificador"], "nome": q["nome"], "cidade": q["cidade"], "uf": q["uf"],
                          "lat_rbba": lat, "lon_rbba": lon, "dist_km_ao_centroide": round(d, 1)})
dists = np.array(dists)
check(not nao_casados, f"Todos os 192 bancos casam com um município IBGE (não casados: {nao_casados})")
log(f"Distância ponto RBBA x centroide do município (km): mediana={np.median(dists):.1f} p90={np.percentile(dists,90):.1f} máx={dists.max():.1f}")
check(len(anomalias) == 2, f"Pontos RBBA com coordenada incoerente (>100 km do próprio município) = {len(anomalias)} -> {[a['id'] for a in anomalias]}")
for a in anomalias:
    log(f"   ANOMALIA RAW (não corrigida no RAW): {a}")
# geo_quality (derivação documentada em DATA_DICTIONARY.md): SUSPEITA > 100 km | REVISAR 25-100 km | OK <= 25 km do centroide do município
gq = Counter("SUSPEITA" if d > 100 else "REVISAR" if d > 25 else "OK" for d in dists)
log(f"geo_quality dos 192 pontos RBBA: {dict(gq)}")
check(gq["SUSPEITA"] == 2 and gq["REVISAR"] == 3 and gq["OK"] == 187, f"geo_quality RBBA: SUSPEITA=2, REVISAR=3, OK=187 (obtido {dict(gq)})")
k = rbba["kpis"]
check(abs(k["kg_perdidos"] / k["kg_recebidos"] - k["pct_perda"]) < 1e-3, "KPI pct_perda = kg_perdidos/kg_recebidos")
PROFILE["rbba"] = {
    "kpis": k,
    "n_pontos": len(feats),
    "municipios_distintos_com_ponto": len({(norm(f['properties']['cidade']), f['properties']['uf']) for f in feats}),
    "anomalias_coordenadas": anomalias,
    "geo_quality_contagem": dict(gq),
    "dist_km_ponto_vs_centroide": {"mediana": float(np.median(dists)), "p90": float(np.percentile(dists, 90))},
    "ano": rbba["ano"],
    "mensal_kg": rbba["graficos"]["mensal"],
    "origens_top": rbba["graficos"]["origens"],
    "classificacao_nova": rbba["graficos"]["classificacao"],
    "modalidades": rbba["graficos"]["modalidades"],
    "operacionais": rbba["graficos"]["operacionais"],
    "perdas_momento": rbba["graficos"]["perdas_momento"],
}

# ---------------------------------------------------------------- PAA
log("\n--- 4. PAA (MDS) ---")
paa = pd.read_csv(RAW / "paa_mds/paa_execucao_compra_doacao_simultanea.csv")
col_kg = "paa_qtd_alim_adquiridos_exec_compra_doacao_simul_d"
check(len(paa) == 49627, f"PAA compra c/ doação simultânea: {len(paa)} linhas")
check(paa[col_kg].notna().all() and (paa[col_kg] >= 0).all(), "PAA kg: sem nulos e sem negativos")
paa["mes"] = paa.anomes_s % 100
paa["ano"] = paa.anomes_s // 100
por_ano = paa.groupby("ano")[col_kg].agg(["sum", "count"])
log("kg e nº de registros por ano (cobertura de registros varia muito entre anos):\n" + por_ano.to_string())
sazo = paa[paa.ano.between(2021, 2025)].groupby("mes")[col_kg].sum()
indice = (sazo / sazo.mean()).round(3)
log("Índice sazonal PAA (kg/mês ÷ média; 2021-2025; PROXY de sazonalidade de oferta agrícola):\n" + indice.to_string())
PROFILE["paa"] = {"n_linhas": int(len(paa)), "indice_sazonal_mes": {int(m): float(v) for m, v in indice.items()},
                  "kg_por_ano": {int(a): float(v) for a, v in por_ano["sum"].items()},
                  "registros_por_ano": {int(a): int(v) for a, v in por_ano["count"].items()},
                  "aviso": "PAA traz apenas totais por município-mês (kg, R$, nº agricultores); NÃO traz produto/categoria."}
join6 = set(paa.codigo_ibge.astype(int)) & {c // 10 for c in codes7}
paa_cods = set(paa.codigo_ibge.astype(int))
check(paa_cods <= {c // 10 for c in codes7}, "PAA: todo codigo_ibge (6 díg.) existe no IBGE")
log(f"PAA compra c/ doação simultânea: {len(paa_cods)} municípios distintos com execução em 2021-2026 (cobertura parcial real, não falha)")
PROFILE["paa"]["municipios_distintos_com_execucao"] = len(paa_cods)

# ---------------------------------------------------------------- OSC completo
log("\n--- 5. IPEA / Mapa das OSCs — leitura COMPLETA em chunks ---")
area_cols = ["Habitação", "Saúde", "Cultura e recreação", "Educação e pesquisa", "Assistência social", "Religião",
             "Associações patronais, profissionais e de produtores rurais", "Meio ambiente e proteção animal",
             "Desenvolvimento e defesa de direitos", "Outros", "Outras atividades associativas"]
sub_cols_food = ["Ass Social sub Assistência social", "Ass Social sub Outros", "Desenv e Def sub Centros e associações comunitárias"]
n = 0
ids_seen, cnpj_seen = set(), set()
dup_id = dup_cnpj = 0
sem_muni = 0
area_cnt = Counter()
sub_cnt = Counter()
nat_cnt = Counter()
uf_cnt = Counter()
muni_all, muni_as, muni_cand = Counter(), Counter(), Counter()
cnpj_bad = 0
cand_n = 0
usecols = ["id_osc", "cd_identificador_osc", "cd_natureza_juridica_osc", "edmu_cd_municipio", "eduf_sg_uf", "dt_fundacao_osc"] + area_cols + sub_cols_food
for ch in pd.read_csv(RAW / "ipea_osc/area_subarea.csv", sep=";", usecols=usecols, chunksize=200_000, low_memory=False):
    n += len(ch)
    for v in ch.id_osc:
        if v in ids_seen: dup_id += 1
        ids_seen.add(v)
    for v in ch.cd_identificador_osc:
        if v in cnpj_seen: dup_cnpj += 1
        cnpj_seen.add(v)
    cnpj_bad += int((ch.cd_identificador_osc.astype(str).str.len() > 14).sum())
    sem_muni += int(ch.edmu_cd_municipio.isna().sum())
    for a in area_cols:
        area_cnt[a] += int((ch[a].fillna(0) == 1).sum())
    for a in sub_cols_food:
        sub_cnt[a] += int((ch[a].fillna(0) == 1).sum())
    nat_cnt.update(ch.cd_natureza_juridica_osc.value_counts().to_dict())
    uf_cnt.update(ch.eduf_sg_uf.value_counts().to_dict())
    muni_all.update(ch.edmu_cd_municipio.dropna().astype(int).value_counts().to_dict())
    as_mask = (ch["Assistência social"].fillna(0) == 1) | (ch["Ass Social sub Assistência social"].fillna(0) == 1)
    muni_as.update(ch.loc[as_mask, "edmu_cd_municipio"].dropna().astype(int).value_counts().to_dict())
    cand_mask = as_mask | (ch["Desenv e Def sub Centros e associações comunitárias"].fillna(0) == 1)
    cand_n += int(cand_mask.sum())
    muni_cand.update(ch.loc[cand_mask, "edmu_cd_municipio"].dropna().astype(int).value_counts().to_dict())
check(n == 960_315, f"OSC: linhas lidas (100% do arquivo) = {n:,}")
log(f"id_osc duplicados={dup_id} | CNPJ duplicados={dup_cnpj} | sem município={sem_muni} | CNPJ com >14 dígitos={cnpj_bad}")
check(dup_id == 0, "OSC: id_osc único")
check(set(muni_all) <= codes7, f"OSC: todos os códigos de município existem no IBGE (fora do IBGE: {len(set(muni_all)-codes7)})")
check(set(muni_all) <= set(cent.index), "OSC: todos os municípios têm centroide (distância ONG-doador calculável)")
log(f"Municípios distintos com ao menos 1 OSC: {len(muni_all)} de 5571")
log(f"OSC por área de atuação (flag=1): {dict(area_cnt)}")
log(f"OSC com 'Assistência social' (área ou subárea): {sum(muni_as.values()):,} em {len(muni_as)} municípios")
log(f"OSC candidatas a receptor (Assistência social OU centros/associações comunitárias): {cand_n:,} em {len(muni_cand)} municípios")
check(cand_n > 0, "Existe universo real de ONGs candidatas")
check(sum(muni_as.values()) == area_cnt["Assistência social"], "Toda OSC de 'Assistência social' tem município (nenhuma cai em location_precision=NONE)")
log(f"location_precision esperado: RBBA EXACT=190, RBBA MUNICIPALITY_CENTROID=2, OSC MUNICIPALITY_CENTROID={n - sem_muni:,}, OSC NONE={sem_muni}")
PROFILE["osc"] = {
    "n_linhas": n, "sem_municipio": sem_muni, "n_cnpj_distintos": len(cnpj_seen), "municipios_com_osc": len(muni_all),
    "por_area_flag1": dict(area_cnt), "sub_flags_relevantes": dict(sub_cnt),
    "assistencia_social_total": int(sum(muni_as.values())), "municipios_com_assistencia_social": len(muni_as),
    "candidatas_receptor_total": cand_n, "municipios_com_candidata": len(muni_cand),
    "top_natureza_juridica": {str(k_): int(v) for k_, v in nat_cnt.most_common(10)},
    "por_uf": {k_: int(v) for k_, v in uf_cnt.most_common()},
    "campos_AUSENTES": ["coordenadas", "endereço/CEP", "capacidade de armazenamento", "refrigeração", "horário de funcionamento", "tipos de alimento aceitos"],
    "aviso_area_alimentar": "Não existe subárea de 'segurança alimentar' nas colunas; a regra de elegibilidade é um PROXY (assistência social / centros comunitários).",
}

# ---------------------------------------------------------------- saída
log("\n--- 6. Regras de escopo ---")
hdr = pd.read_csv(RAW / "ipea_osc/area_subarea.csv", sep=";", nrows=0).columns
check(not any(("cpf" in c.lower() or "socio" in c.lower() or "pessoa_fisica" in c.lower()) for c in hdr), "OSC: nenhuma coluna de CPF/sócio/pessoa física no arquivo")
check(not any(("beneficiari" in c.lower()) for c in hdr), "OSC: nenhuma coluna de beneficiário final")
log("Nenhum dado simulado foi gerado por este script.")
log("\n" + "=" * 70)
log("RESULTADO: " + ("TODOS OS TESTES PASSARAM" if not FAILS else f"{len(FAILS)} FALHA(S): {FAILS}"))
log("=" * 70)
(ROOT / "docs" / "data" / "VALIDATION_LOG.txt").write_text("\n".join(LOG), encoding="utf-8")
(ROOT / "docs" / "data" / "PHASE0_PROFILE.json").write_text(json.dumps(PROFILE, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
sys.exit(1 if FAILS else 0)
