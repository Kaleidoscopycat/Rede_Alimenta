"""Relatório automático de qualidade de dados (schema, nulos, duplicados, formatos, coordenadas, código IBGE, datas, faixas, PII).

Uso: python -m quality.data_quality [--sim-tag main]  →  docs/data/DATA_QUALITY_REPORT.md + data/metadata/quality_report.json
Lê apenas camadas silver/gold e simulated; nunca altera RAW."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PII_COLS = re.compile(r"cpf|rg$|telefone|celular|email|e_mail|nome_responsavel|nome_pessoa|endereco|logradouro|data_nasc|religi", re.I)
# area_religiao = flag IPEA de ÁREA DE ATUAÇÃO da organização (atributo de pessoa jurídica), não religião de pessoa. Ressalva documentada.
ALLOWED = {"area_religiao"}
PII_VALUE = {"cpf": re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"), "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "telefone": re.compile(r"\(?\d{2}\)?\s?9?\d{4}-?\d{4}")}

TABLES = {
    "silver/osc": dict(key="ong_id"), "silver/rbba": dict(key="ong_id"), "silver/municipios": dict(key="codigo_ibge"),
    "gold/organizations": dict(key="ong_id", ranges={"lat": (-34, 6), "lon": (-75, -28), "populacao_2026": (0, 2e7)}),
    "gold/territory": dict(key="codigo_ibge", ranges={"latitude": (-34, 6), "longitude": (-75, -28), "populacao_2026": (0, 2e7)}),
}
SIM = {
    "sim_donor": dict(key="donor_id", ranges={"lat": (-34, 6), "lon": (-75, -28)}),
    "sim_lot": dict(key="lot_id", ranges={"quantidade_kg": (0, 1e5), "dias_ate_validade": (0, 400), "horas_ate_validade": (0, 24 * 400)}),
    "sim_ong_declared": dict(key="ong_id"), "sim_fleet": dict(key="ong_id", ranges={"capacidade_kg": (0, 3e4)}),
    "sim_pair_outcome": dict(key=["lot_id", "ong_id"], ranges={"dist_km": (0, 160), "tempo_deslocamento_est_h": (0, 24 * 10)}),
}


def check_table(name: str, df: pd.DataFrame, spec: dict, municipios: set | None) -> dict:
    r: dict = {"tabela": name, "linhas": int(len(df)), "colunas": int(df.shape[1])}
    r["nulos_pct"] = {c: round(float(v), 4) for c, v in df.isna().mean().items() if v > 0}
    key = spec.get("key")
    if key:
        r["chave"] = key
        r["duplicados_chave"] = int(df.duplicated(key).sum())
    r["linhas_duplicadas_completas"] = int(df.astype(str).duplicated().sum()) if len(df) < 200_000 else None
    r["colunas_pii_por_nome"] = [c for c in df.columns if PII_COLS.search(c) and c not in ALLOWED]
    pii_v = {}
    for c in df.select_dtypes(include="object").columns[:40]:
        if c.endswith("_id") or c in ("native_id", "source_id"):
            continue  # identificadores pseudonimizados (hash hex) geram falsos positivos de telefone
        s = df[c].dropna().astype(str).head(20000)
        for k, rx in PII_VALUE.items():
            n = int(s.str.contains(rx).sum())
            if n:
                pii_v[f"{c}:{k}"] = n
    r["pii_por_valor"] = pii_v
    rg = {}
    for c, (lo, hi) in (spec.get("ranges") or {}).items():
        if c in df:
            x = pd.to_numeric(df[c], errors="coerce")
            rg[c] = {"min": float(x.min()), "max": float(x.max()), "fora_da_faixa": int(((x < lo) | (x > hi)).sum())}
    r["faixas"] = rg
    for c in df.columns:
        if "ibge" in c and df[c].dtype != object and municipios is not None and c in ("municipio_ibge", "codigo_ibge"):
            s = df[c].dropna().astype("int64")
            r.setdefault("codigo_ibge", {})[c] = {"invalidos_formato": int((~s.between(1_000_000, 9_999_999)).sum()), "inexistentes": int((~s.isin(municipios)).sum())}
    dtc = [c for c in df.columns if str(df[c].dtype).startswith("datetime")]
    for c in dtc:
        x = df[c].dropna()
        r.setdefault("datas", {})[c] = {"min": str(x.min()), "max": str(x.max()), "futuras": int((x > pd.Timestamp.now() + pd.Timedelta(days=366)).sum())}
    if "data_origin" in df:
        r["data_origin"] = {k: int(v) for k, v in df["data_origin"].value_counts().items()}
    return r


def run(sim_tag: str = "main") -> dict:
    terr = pd.read_parquet(ROOT / "data/gold/territory.parquet")
    muni = set(terr.codigo_ibge.astype("int64"))
    res = {"gerado_em": dt.datetime.now(dt.timezone.utc).isoformat(), "sim_tag": sim_tag, "reais": [], "simuladas": []}
    for n, s in TABLES.items():
        res["reais"].append(check_table(n, pd.read_parquet(ROOT / "data" / f"{n}.parquet"), s, muni))
    for n, s in SIM.items():
        res["simuladas"].append(check_table(n, pd.read_parquet(ROOT / "data/simulated" / sim_tag / f"{n}.parquet"), s, muni))
    # coerência geográfica real
    o = pd.read_parquet(ROOT / "data/gold/organizations.parquet")
    res["geo_organizacoes"] = {"location_precision": {k: int(v) for k, v in o.location_precision.value_counts().items()}, "geo_quality": {k: int(v) for k, v in o.geo_quality.value_counts().items()},
                               "rankable_by_distance": int(o.rankable_by_distance.sum()), "total": int(len(o))}
    probs = []
    for grp in ("reais", "simuladas"):
        for t in res[grp]:
            if t.get("duplicados_chave"):
                probs.append(f"{t['tabela']}: {t['duplicados_chave']} chaves duplicadas")
            if t["colunas_pii_por_nome"]:
                probs.append(f"{t['tabela']}: colunas com nome de PII {t['colunas_pii_por_nome']}")
            if t["pii_por_valor"]:
                probs.append(f"{t['tabela']}: PII por valor {t['pii_por_valor']}")
            for c, v in t["faixas"].items():
                if v["fora_da_faixa"]:
                    probs.append(f"{t['tabela']}.{c}: {v['fora_da_faixa']} valores fora da faixa")
            for c, v in (t.get("codigo_ibge") or {}).items():
                if v["invalidos_formato"] or v["inexistentes"]:
                    probs.append(f"{t['tabela']}.{c}: IBGE inválido/inexistente {v}")
    res["problemas"] = probs
    res["status"] = "OK" if not probs else "COM_ACHADOS"
    return res


def to_md(r: dict) -> str:
    L = ["# Relatório de qualidade de dados (automático)", "", f"Gerado em {r['gerado_em']} por `python -m quality.data_quality` (conjunto simulado: `{r['sim_tag']}`).", "",
         f"**Status:** {r['status']}", ""]
    L += ["## Achados", ""] + ([f"- {p}" for p in r["problemas"]] or ["- Nenhum achado automático."]) + [""]
    for titulo, grp in (("Dados REAIS (silver/gold, data_origin=PUBLIC)", "reais"), ("Dados SIMULADOS (data_origin=SIMULATED)", "simuladas")):
        L += [f"## {titulo}", "", "| Tabela | Linhas | Cols | Dup. chave | Colunas c/ nulos | PII (nome/valor) |", "|---|---:|---:|---:|---:|---|"]
        for t in r[grp]:
            L.append(f"| {t['tabela']} | {t['linhas']:,} | {t['colunas']} | {t.get('duplicados_chave', '-')} | {len(t['nulos_pct'])} | {len(t['colunas_pii_por_nome'])}/{len(t['pii_por_valor'])} |".replace(",", "."))
        L.append("")
        for t in r[grp]:
            if t["nulos_pct"]:
                top = sorted(t["nulos_pct"].items(), key=lambda kv: -kv[1])[:6]
                L.append(f"- `{t['tabela']}` maiores % de nulos: " + ", ".join(f"{c} {v*100:.1f}%" for c, v in top))
            for c, v in t["faixas"].items():
                L.append(f"- `{t['tabela']}.{c}`: min {v['min']:.3g}, max {v['max']:.3g}, fora da faixa: {v['fora_da_faixa']}")
        L.append("")
    g = r["geo_organizacoes"]
    L += ["## Geografia das organizações (REAL)", "", f"- `location_precision`: {g['location_precision']}", f"- `geo_quality`: {g['geo_quality']}",
          f"- ranqueáveis por distância: {g['rankable_by_distance']} de {g['total']}", ""]
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--sim-tag", default="main"); a = ap.parse_args()
    r = run(a.sim_tag)
    (ROOT / "data/metadata").mkdir(exist_ok=True, parents=True)
    (ROOT / "data/metadata/quality_report.json").write_text(json.dumps(r, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (ROOT / "docs/data/DATA_QUALITY_REPORT.md").write_text(to_md(r), encoding="utf-8")
    print(r["status"], *r["problemas"][:10], sep="\n")
