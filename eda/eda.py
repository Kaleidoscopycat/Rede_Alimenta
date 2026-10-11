"""EDA automática. Seções separadas: DADOS REAIS (PUBLIC) e DADOS SIMULADOS (SIMULATED). Gera docs/data/EDA.md e docs/data/eda_figs/*.png."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "docs/data/eda_figs"
FIG.mkdir(parents=True, exist_ok=True)


def md(df: pd.DataFrame, fmt="{:,.2f}") -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(map(str, [df.index.name or ""] + cols)) + " |", "|" + "---|" * (len(cols) + 1)]
    for i, r in df.iterrows():
        out.append("| " + " | ".join([str(i)] + [(fmt.format(v) if isinstance(v, (float, np.floating)) else (f"{v:,}" if isinstance(v, (int, np.integer)) else str(v))) for v in r]) + " |")
    return "\n".join(out).replace(",", "§").replace(".", ",").replace("§", ".") if False else "\n".join(out)


def main(tag: str = "main"):
    org = pd.read_parquet(ROOT / "data/gold/organizations.parquet")
    terr = pd.read_parquet(ROOT / "data/gold/territory.parquet")
    S = ROOT / "data/simulated" / tag
    pairs = pd.read_parquet(S / "sim_pair_outcome.parquet", columns=["lot_id", "ong_id", "dist_km", "rank_distancia", "elegivel_regra", "resposta", "coletou", "target", "horas_resposta", "horas_ate_coleta", "tem_frota", "mesmo_municipio"])
    lot = pd.read_parquet(S / "sim_lot.parquet")
    don = pd.read_parquet(S / "sim_donor.parquet")
    txt = pd.read_parquet(S / "sim_lot_text.parquet", columns=["y_categoria", "difficulty_flags", "y_validity_source", "text_split", "template_family_id"])
    ref = json.loads((ROOT / "data/bronze/rbba_referencia.json").read_text(encoding="utf-8")) if (ROOT / "data/bronze/rbba_referencia.json").exists() else {}
    real = json.loads((S / "realism.json").read_text(encoding="utf-8"))
    L = ["# EDA — Rede Alimenta IA (Fase 1)", "", "Gerado automaticamente por `python -m eda.eda`. **Seção A = dados REAIS (`data_origin=PUBLIC`). Seção B = dados SIMULADOS (`data_origin=SIMULATED`).** Nada de B deve ser lido como fato do mundo real.", ""]
    # ------------------------------------------------------------- A: REAL
    L += ["## A. Dados REAIS", "", "### A.1 Organizações (gold/organizations)", ""]
    L += [f"- Total: **{len(org):,}** organizações (`ong_tipo`: " + ", ".join(f"{k} {v:,}" for k, v in org.ong_tipo.value_counts().items()) + ").",
          f"- Ranqueáveis por distância (coordenada utilizável): **{int(org.rankable_by_distance.sum()):,}** ({org.rankable_by_distance.mean()*100:.1f}%).",
          "- `location_precision`: " + ", ".join(f"{k} {v:,}" for k, v in org.location_precision.value_counts().items()) + ".",
          "- `geo_quality`: " + ", ".join(f"{k} {v:,}" for k, v in org.geo_quality.value_counts().items()) + ".", ""]
    uf = org.groupby("uf").agg(orgs=("ong_id", "size"), ranqueaveis=("rankable_by_distance", "sum"), bancos=("ong_tipo", lambda s: int((s == "BANCO_ALIMENTOS_RBBA").sum())))
    pop = terr.groupby("uf").populacao_2026.sum()
    uf["pop_milhoes"] = pop / 1e6
    uf["orgs_por_100mil_hab"] = uf.orgs / (pop / 1e5)
    uf = uf.sort_values("orgs_por_100mil_hab")
    L += ["### A.2 Cobertura por UF (organizações por 100 mil habitantes)", "", "Extremos (vieses de cobertura do cadastro IPEA/OSC e da RBBA):", "", md(pd.concat([uf.head(5), uf.tail(5)]), "{:,.2f}"), ""]
    L += ["Viés: o cadastro IPEA/OSC cobre organizações formais; ONGs informais (as que mais recebem doação direta) estão **ausentes**. A RBBA cobre só bancos de alimentos da rede. Distribuição por UF segue o cadastro, não a necessidade.", ""]
    mun = org.groupby("municipio_ibge").size()
    L += [f"- Municípios com ≥1 organização: **{(mun>0).sum():,}** de {len(terr):,}; sem nenhuma: {len(terr)-(mun>0).sum():,}. Mediana de organizações por município com ≥1: {mun.median():.0f}.", ""]
    if ref:
        L += ["### A.3 Referência agregada RBBA (REAL, agregada)", "", "```json", json.dumps({k: ref[k] for k in list(ref)[:6]}, ensure_ascii=False, indent=1)[:1200], "```", ""]
    fig, ax = plt.subplots(figsize=(8, 4)); uf.orgs_por_100mil_hab.sort_values().plot.bar(ax=ax); ax.set_title("REAL — organizações por 100 mil hab. por UF"); plt.tight_layout(); fig.savefig(FIG / "real_orgs_por_uf.png", dpi=110); plt.close(fig)
    # ------------------------------------------------------------- B: SIMULADO
    L += ["## B. Dados SIMULADOS", "", f"Conjunto `{tag}` — {real['dataset_version']}; cenário {real['scenario']}. Rótulo obrigatório: *calculado sobre dados SIMULADOS*.", "",
          f"- Lotes: **{len(lot):,}**; doadores: **{len(don):,}**; pares candidatos: **{len(pairs):,}**; target médio: **{pairs.target.mean():.3f}**.", ""]
    mix = lot.groupby("categoria").agg(lotes=("lot_id", "size"), kg_total=("quantidade_kg", "sum"), kg_mediana=("quantidade_kg", "median"), validade_mediana_dias=("dias_ate_validade", "median"))
    mix["pct_lotes"] = mix.lotes / mix.lotes.sum() * 100
    L += ["### B.1 Mix de lotes por categoria", "", md(mix.sort_values("lotes", ascending=False), "{:,.1f}"), ""]
    L += ["Comparação com referências (`realism.json`):", ""]
    for k in ("R2", "R3", "R4", "R6"):
        c = real["checks"][k]
        L.append(f"- **{k} ({c['status']})** — {c['descricao']}.")
    L += ["", "- **R1 NÃO PASSA (registrado, não escondido):** volume anual simulado por banco de alimentos é ~2 ordens de grandeza menor que a referência RBBA (411,7 t/relatório/ano) porque o simulador gera apenas o fluxo de doadores do universo simulado, sem calibrar o volume por banco.",
          f"- **R6:** {real['checks']['R6']['sim_kg_sem_destino_pct']:.1f}% do kg simulado fica sem nenhum destino dentro da validade, contra ~4,85% de perda reportada pela RBBA: o simulador é **pessimista** quanto ao sucesso do desfecho; as taxas absolutas de sucesso não devem ser usadas como estimativa real.", ""]
    resp = pairs.resposta.value_counts(normalize=True) * 100
    L += ["### B.2 Desfecho simulado", "", "- Resposta: " + ", ".join(f"{k} {v:.1f}%" for k, v in resp.items()) + f"; coleta {pairs.coletou.mean()*100:.1f}%; target (coletou dentro da validade) {pairs.target.mean()*100:.1f}%.",
          f"- Pares elegíveis pela regra: {pairs.elegivel_regra.mean()*100:.1f}%; taxa de sucesso entre elegíveis {pairs[pairs.elegivel_regra].target.mean()*100:.1f}% vs não elegíveis {pairs[~pairs.elegivel_regra].target.mean()*100:.1f}% (elegível ≠ sucesso: desfecho estocástico).", ""]
    bins = pd.cut(pairs.dist_km, [-1, 0.001, 15, 30, 60, 100, 160]); t_d = pairs.groupby(bins, observed=True).target.agg(["mean", "size"]); t_d["mean"] *= 100
    L += ["Taxa de sucesso por distância (SIMULADO):", "", md(t_d.rename(columns={"mean": "target_%", "size": "pares"}).astype({"pares": int}), "{:,.1f}"), ""]
    hr = pairs.horas_resposta.dropna()
    L += [f"- Tempo de resposta simulado (h): mediana {hr.median():.1f}, p90 {hr.quantile(.9):.1f}. Tempo até coleta (h): mediana {pairs.horas_ate_coleta.dropna().median():.1f}.", ""]
    diff = txt.difficulty_flags.fillna("nenhum").str.split("|").explode().value_counts(normalize=True) * 100
    L += ["### B.3 Textos simulados", "", "- Famílias de template: " + ", ".join(f"{k} {v:,}" for k, v in txt.template_family_id.value_counts().items()) + " (F4 reservada = teste fora do treino).",
          "- Validade: " + ", ".join(f"{k} {v*100:.1f}%" for k, v in txt.y_validity_source.value_counts(normalize=True).items()) + ".",
          "- Casos difíceis (% dos textos): " + ", ".join(f"{k} {v:.1f}" for k, v in diff.head(8).items()) + ".",
          "- **Lacuna:** não existe nenhum corpus REAL de descrições de doação; os textos são gerados por templates da equipe. A avaliação em texto real depende do conjunto `MANUALLY_LABELED`, ainda inexistente.", ""]
    L += ["### B.4 Vieses e limitações", "",
          "- Circularidade: modelos aprendem o simulador; métricas medem aderência às premissas do gerador, não desempenho real.",
          "- Doadores sintéticos: população como proxy da densidade de estabelecimentos (base de CNPJ não obtida).",
          "- Localização do doador = centroide do município (`MUNICIPALITY_CENTROID`); distâncias dentro do mesmo município são 0 e rankings dentro do município dependem de atributos, não de distância.",
          "- Rótulos contrafactuais: todos os pares candidatos têm desfecho, o que não ocorre em produção (só se observa o par acionado).", ""]
    fig, ax = plt.subplots(figsize=(8, 4)); mix.sort_values("lotes").pct_lotes.plot.barh(ax=ax); ax.set_title("SIMULADO — % de lotes por categoria"); plt.tight_layout(); fig.savefig(FIG / "sim_mix_categoria.png", dpi=110); plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, 4)); (t_d["mean"]).plot.bar(ax=ax); ax.set_title("SIMULADO — target % por faixa de distância (km)"); plt.tight_layout(); fig.savefig(FIG / "sim_target_por_distancia.png", dpi=110); plt.close(fig)
    L += ["Figuras: `docs/data/eda_figs/` (`real_orgs_por_uf.png`, `sim_mix_categoria.png`, `sim_target_por_distancia.png`).", ""]
    (ROOT / "docs/data/EDA.md").write_text("\n".join(L), encoding="utf-8")
    print("EDA ok", len(L))


if __name__ == "__main__":
    main()
