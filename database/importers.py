"""Importadores do banco. REGRAS (AGENTS.md):
* Organizações/municípios/indicadores: SOMENTE de data/gold (pipeline REAL da Fase 1), com rastreabilidade (source, source_record_id, source_url, last_verified_at).
* Dados simulados: SOMENTE de data/simulated/<tag> e SOMENTE se a coluna `data_origin` da origem for SIMULATED (senão aborta; nunca reclassifica).
* Nada é inventado aqui: nenhuma linha é criada fora dos arquivos de origem.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from core.settings import TZ
from database import models as m

log = logging.getLogger("importers")
ROOT = Path(__file__).resolve().parents[1]
NS = uuid.UUID("6f0d1c7a-52e1-4f0a-9d53-5a4a1d0c9b11")  # namespace fixo p/ UUIDs determinísticos (reprodutibilidade)
CHUNK = 5000

# Estado de revisão de licença por fonte (DATA_LICENSES.md v3). NADA aqui marca algo como liberado sem confirmação formal.
SOURCE_META: dict[str, dict[str, Any]] = {
    "ipea_osc_area": dict(organization="IPEA", review="NEEDS_REVIEW", commercial="NAO_CONFIRMADO", cleared=False,
                          note="Other (Attribution) — uso comercial não confirmado; confirmar termos do Mapa das OSCs / e-mail formal ao IPEA"),
    "rbba_resumo": dict(organization="MDS / Alimenta Cidades (RBBA)", review="NEEDS_REVIEW", commercial="NAO_CONFIRMADO", cleared=False,
                        note="Licença não declarada; endpoint não documentado — e-mail a cgesan@mds.gov.br"),
    "ibge_municipios": dict(organization="IBGE", review="NEEDS_REVIEW", commercial="NAO_CONFIRMADO", cleared=False,
                            note="Dado aberto; licença explícita não localizada — citar termos oficiais de reutilização"),
    "ibge_populacao": dict(organization="IBGE", review="NEEDS_REVIEW", commercial="NAO_CONFIRMADO", cleared=False,
                           note="Dado aberto; licença explícita não localizada — citar termos oficiais de reutilização"),
    "ibge_coords": dict(organization="kelvins/municipios-brasileiros (terceiros)", review="NEEDS_REVIEW", commercial="MIT_REPO_ORIGEM_NAO_CONFIRMADA", cleared=False,
                        note="MIT é do repositório; origem primária das coordenadas não confirmada (PROXY) — substituir pela malha oficial IBGE"),
    "paa_compra_doacao": dict(organization="MDS/SAGI", review="APPROVED", commercial="PERMITIDO_CC_BY_A_REVERIFICAR", cleared=False,
                              note="CC-BY (metadado dados.gov.br); reverificar no portal e atribuir MDS"),
    "paa_municipios": dict(organization="MDS/SAGI", review="APPROVED", commercial="PERMITIDO_CC_BY_A_REVERIFICAR", cleared=False,
                           note="CC-BY (metadado dados.gov.br); reverificar no portal e atribuir MDS"),
}
ORG_SOURCE_URL = {"ipea_osc_area": "https://dados.gov.br/dados/conjuntos-dados/mapaosc", "rbba_resumo": "https://alimentacidades.digital/rbba/api/resumo"}


def _chunks(rows: list[dict], n: int = CHUNK) -> Iterable[list[dict]]:
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def _bulk(session: Session, model, rows: list[dict]) -> int:
    for c in _chunks(rows):
        session.execute(insert(model), c)
    return len(rows)


def _nn(v: Any) -> Any:
    """NaN/NA -> None; numpy -> python."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        return v.item()
    return v


def _manifest() -> dict:
    return json.loads((ROOT / "data" / "metadata" / "ingestion_manifest.json").read_text(encoding="utf-8"))


def _ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


# ------------------------------------------------------------------ fontes públicas
def import_public_sources(session: Session) -> dict[str, int]:
    man = _manifest()
    pv = man["pipeline_version"]
    n_src = n_ver = 0
    for sid, meta in SOURCE_META.items():
        s = man["sources"][sid]
        if session.get(m.PublicDataSource, sid) is None:
            session.add(m.PublicDataSource(
                id=sid, name=s["source_name"], organization=meta["organization"], dataset=s.get("source_dataset"), url=s.get("source_url"),
                license_status=f"{s.get('license_status')} | {meta['note']}", review_status=meta["review"], commercial_use=meta["commercial"],
                publication_cleared=meta["cleared"], raw_sha256=s.get("raw_sha256"), ingested_at=_ts(s["ingested_at"]), source_updated_at=s.get("source_updated_at")))
            n_src += 1
        label = f"pipeline-{pv}+raw:{str(s.get('raw_sha256'))[:12]}"
        if session.scalar(select(m.PublicDatasetVersion.id).where(m.PublicDatasetVersion.source_id == sid, m.PublicDatasetVersion.version_label == label)) is None:
            session.add(m.PublicDatasetVersion(source_id=sid, version_label=label, raw_sha256=s.get("raw_sha256"), n_records=int(s.get("n_records_raw") or 0),
                                               pipeline_version=pv, ingested_at=_ts(s["ingested_at"])))
            n_ver += 1
    session.flush()
    return {"sources": n_src, "dataset_versions": n_ver}


def _version_id(session: Session, sid: str) -> int:
    return session.scalars(select(m.PublicDatasetVersion.id).where(m.PublicDatasetVersion.source_id == sid).order_by(m.PublicDatasetVersion.id.desc())).first()


# ------------------------------------------------------------------ municípios e indicadores
INDICATORS = [("populacao_2026", "populacao_2026", "habitantes", "2026", "ibge_populacao"),
              ("n_osc_assistencia_municipio", "n_osc_assistencia_municipio", "organizações", "snapshot IPEA", "ipea_osc_area"),
              ("n_banco_rbba_municipio", "n_banco_rbba_municipio", "bancos", "RBBA 2025", "rbba_resumo"),
              ("paa_kg_historico_municipio", "paa_kg_historico_municipio", "kg", "PAA histórico", "paa_compra_doacao"),
              ("paa_adesao", "paa_adesao", "0/1", "2026", "paa_municipios")]


def import_municipalities(session: Session) -> dict[str, int]:
    t = pd.read_parquet(ROOT / "data" / "gold" / "territory.parquet")
    if not (t["data_origin"] == "PUBLIC").all():
        raise ValueError("territory deve ser PUBLIC")
    if session.scalar(select(m.Municipality.ibge_code).limit(1)) is not None:
        return {"municipalities": 0, "indicators": 0}
    vid = _version_id(session, "ibge_municipios")
    rows = [dict(ibge_code=int(r.codigo_ibge), name=r.nome, uf=r.uf, region=r.regiao, lat=_nn(r.latitude), lon=_nn(r.longitude), location_precision=r.location_precision,
                 coord_origin=r.coord_origin, source_id="ibge_municipios", dataset_version_id=vid, data_origin="PUBLIC") for r in t.itertuples()]
    n_m = _bulk(session, m.Municipality, rows)
    ind: list[dict] = []
    for code, col, unit, per, sid in INDICATORS:
        v = _version_id(session, sid)
        for r in t[["codigo_ibge", col]].itertuples(index=False):
            val = _nn(r[1])
            if val is not None:
                ind.append(dict(municipio_ibge=int(r[0]), code=code, value=float(val), unit=unit, reference_period=per, source_id=sid, dataset_version_id=v, data_origin="PUBLIC"))
    n_i = _bulk(session, m.PublicIndicator, ind)
    return {"municipalities": n_m, "indicators": n_i}


def import_food_categories(session: Session) -> int:
    from simulation.params import TAXONOMY_FILE
    tax = yaml.safe_load(TAXONOMY_FILE.read_text(encoding="utf-8"))["categories"]
    n = 0
    for code, c in tax.items():
        if session.get(m.FoodCategory, code) is None:
            d = c["days"]
            session.add(m.FoodCategory(code=code, description=c.get("desc", code), perecibilidade=c["perecibilidade"], typical_shelf_days_min=float(d[0]), typical_shelf_days_max=float(d[1]),
                                       unit_mass_kg=c.get("unit_mass_kg", {}), source="taxonomy_v0.2 (PREMISSA DO PROJETO; vida útil e massas unitárias sem fonte)"))
            n += 1
    session.flush()
    return n


# ------------------------------------------------------------------ organizações REAIS
def import_organizations(session: Session) -> dict[str, int]:
    if session.scalar(select(m.Organization.id).limit(1)) is not None:
        return {"organizations": 0, "locations": 0}
    man = _manifest()
    o = pd.read_parquet(ROOT / "data" / "gold" / "organizations.parquet")
    if not (o["data_origin"] == "PUBLIC").all():
        raise ValueError("organizations deve ser PUBLIC (dados reais)")
    verified = {sid: _ts(man["sources"][sid]["ingested_at"]) for sid in ORG_SOURCE_URL}
    orgs, locs = [], []
    for r in o.itertuples(index=False):
        oid = uuid.uuid5(NS, r.ong_id)
        has_pt = _nn(r.lat) is not None and _nn(r.lon) is not None
        orgs.append(dict(id=oid, ong_id=r.ong_id, ong_tipo=r.ong_tipo, source=r.source_id, source_record_id=str(r.native_id), source_url=ORG_SOURCE_URL[r.source_id],
                         last_verified_at=verified[r.source_id], municipio_ibge=_nn(r.municipio_ibge), uf=_nn(r.uf), natureza_juridica=_nn(r.natureza_juridica),
                         ano_fundacao=_nn(r.ano_fundacao), modalidade_rbba=_nn(r.modalidade_rbba),
                         area_assistencia_social=None if _nn(r.area_assistencia_social) is None else bool(r.area_assistencia_social), pipeline_version=r.pipeline_version,
                         license_review_status="NEEDS_REVIEW", platform_status="PUBLIC_RECORD", data_origin="PUBLIC"))
        locs.append(dict(organization_id=oid, lat=_nn(r.lat) if has_pt else None, lon=_nn(r.lon) if has_pt else None,
                         location_precision=r.location_precision if has_pt else "NONE", geo_quality=_nn(r.geo_quality), rankable_by_distance=bool(r.rankable_by_distance) and has_pt,
                         coord_source="RBBA (ponto da própria fonte)" if r.location_precision == "EXACT" else "centroide do município (PROXY_TERCEIROS_MIT)", data_origin="PUBLIC"))
    return {"organizations": _bulk(session, m.Organization, orgs), "locations": _bulk(session, m.OrganizationLocation, locs)}


# ------------------------------------------------------------------ SIMULADOS
def _require_simulated(df: pd.DataFrame, name: str) -> None:
    if not (df["data_origin"] == "SIMULATED").all():
        raise RuntimeError(f"{name}: data_origin diferente de SIMULATED na origem — importação abortada (nunca reclassificar)")
    for c in ("generator_version", "seed", "dataset_version"):
        if df[c].isna().any():
            raise RuntimeError(f"{name}: coluna {c} ausente na origem — importação abortada")


def _trace(r: Any) -> dict:
    return dict(generator_version=r.generator_version, seed=int(r.seed), dataset_version=r.dataset_version, data_origin="SIMULATED")


def import_simulated(session: Session, tag: str = "main", with_lots: bool = True) -> dict[str, Any]:
    base = ROOT / "data" / "simulated" / tag
    decl = pd.read_parquet(base / "sim_ong_declared.parquet")
    fleet = pd.read_parquet(base / "sim_fleet.parquet")
    don = pd.read_parquet(base / "sim_donor.parquet")
    for df, nm in ((decl, "sim_ong_declared"), (fleet, "sim_fleet"), (don, "sim_donor")):
        _require_simulated(df, nm)
    dataset_version = str(don["dataset_version"].iloc[0])
    out: dict[str, Any] = {"dataset_version": dataset_version, "tag": tag}
    org_ids = {r.ong_id: r.id for r in session.execute(select(m.Organization.ong_id, m.Organization.id))}
    if not org_ids:
        raise RuntimeError("importe as organizações reais antes dos dados simulados")
    cat_cols = [c for c in decl.columns if c.startswith("aceita_") and c.endswith("_declarado")]
    # --- perfis declarados das ONGs (SIMULADOS)
    if session.scalar(select(m.OrganizationProfile.organization_id).where(m.OrganizationProfile.dataset_version == dataset_version).limit(1)) is None:
        fl = fleet.set_index("ong_id")
        rows = []
        for r in decl.itertuples(index=False):
            if r.ong_id not in org_ids:
                continue
            f = fl.loc[r.ong_id]
            cats = [c[len("aceita_"):-len("_declarado")] for c in cat_cols if bool(getattr(r, c))]
            rows.append(dict(organization_id=org_ids[r.ong_id], capacity_min_kg_day=_nn(r.capacidade_declarada_faixa_min_kg_dia), capacity_max_kg_day=float(r.capacidade_declarada_faixa_max_kg_dia),
                             cold_chamber=bool(r.camara_fria_declarada), open_hour=float(r.horario_abertura_declarado_h), close_hour=float(r.horario_fechamento_declarado_h),
                             open_days_mask=int(r.dias_funcionamento_declarados_mask), accepted_categories=cats, has_fleet=bool(f["tem_frota"]),
                             fleet_capacity_kg=_nn(f["capacidade_kg"]) if bool(f["tem_frota"]) else None, fleet_refrigerated=bool(f["refrigerado"]) and bool(f["tem_frota"]), **_trace(r)))
        out["org_profiles"] = _bulk(session, m.OrganizationProfile, rows)
    else:
        out["org_profiles"] = 0
    # --- veículos de coleta (SIMULADOS; frota do simulador, só ONGs com tem_frota) — usados pela roteirização (Fase 2 Parte 2)
    if session.scalar(select(m.Vehicle.id).where(m.Vehicle.dataset_version == dataset_version).limit(1)) is None:
        muni = {r.ibge_code: (r.lat, r.lon) for r in session.execute(select(m.Municipality.ibge_code, m.Municipality.lat, m.Municipality.lon))}
        vrows, sem_base = [], 0
        for r in fleet[fleet["tem_frota"].astype(bool)].itertuples(index=False):
            if r.ong_id not in org_ids:
                continue
            base_mun = int(r.base_municipio_ibge)
            lat, lon = muni.get(base_mun, (None, None))
            if lat is None or lon is None:
                sem_base += 1  # base sem coordenada conhecida: nunca inventada; o veículo não é importado
                continue
            vrows.append(dict(id=uuid.uuid5(NS, f"{dataset_version}|vehicle|{r.ong_id}"), organization_id=org_ids[r.ong_id], vehicle_type=str(r.tipo_veiculo), capacity_kg=float(r.capacidade_kg),
                              refrigerated=bool(r.refrigerado), base_municipio_ibge=base_mun, base_lat=float(lat), base_lon=float(lon), location_precision="MUNICIPALITY_CENTROID", **_trace(r)))
        out["vehicles"] = _bulk(session, m.Vehicle, vrows)
        out["vehicles_sem_base_conhecida"] = sem_base
    else:
        out["vehicles"] = 0
    # --- doadores (SIMULADOS)
    donor_ids: dict[str, uuid.UUID] = {}
    if session.scalar(select(m.Donor.id).where(m.Donor.dataset_version == dataset_version).limit(1)) is None:
        drows, lrows = [], []
        for r in don.itertuples(index=False):
            did = uuid.uuid5(NS, f"{dataset_version}|{r.donor_id}")
            donor_ids[r.donor_id] = did
            drows.append(dict(id=did, external_id=r.donor_id, donor_type=r.donor_type, donor_size=r.donor_size, municipio_ibge=int(r.municipio_ibge), pickup_days_mask=int(r.dias_retirada_mask),
                              pickup_start_h=float(r.janela_retirada_inicio_h), pickup_end_h=float(r.janela_retirada_fim_h), load_minutes=int(r.tempo_carga_min), **_trace(r)))
            lrows.append(dict(donor_id=did, lat=float(r.lat), lon=float(r.lon), location_precision=r.location_precision, basis=r.donor_geo_basis, **_trace(r)))
        out["donors"] = _bulk(session, m.Donor, drows)
        out["donor_locations"] = _bulk(session, m.DonorLocation, lrows)
    else:
        donor_ids = {x.external_id: x.id for x in session.execute(select(m.Donor.external_id, m.Donor.id).where(m.Donor.dataset_version == dataset_version))}
        out["donors"] = out["donor_locations"] = 0
    # --- lotes (SIMULADOS) -> donations (HISTORICAL) + itens
    if with_lots and session.scalar(select(m.Donation.id).where(m.Donation.dataset_version == dataset_version).limit(1)) is None:
        lots = pd.read_parquet(base / "sim_lot.parquet")
        txt = pd.read_parquet(base / "sim_lot_text.parquet", columns=["lot_id", "texto", "data_origin"])
        _require_simulated(lots, "sim_lot")
        if not (txt["data_origin"] == "SIMULATED").all():
            raise RuntimeError("sim_lot_text com data_origin != SIMULATED")
        lots = lots.merge(txt[["lot_id", "texto"]], on="lot_id", how="left")
        now = dt.datetime.now(dt.timezone.utc)
        drows, irows = [], []
        for r in lots.itertuples(index=False):
            created = r.created_at.to_pydatetime().replace(tzinfo=TZ)  # relógio SIMULADO (data de cadastro simulada)
            did = uuid.uuid5(NS, f"{dataset_version}|{r.lot_id}")
            drows.append(dict(id=did, donor_id=donor_ids[r.donor_id], status="HISTORICAL", entry_channel="SIMULATOR_IMPORT", external_id=r.lot_id, raw_text=_nn(r.texto),
                              categoria=r.categoria, perecibilidade=r.perecibilidade, exige_refrigeracao=bool(r.exige_refrigeracao), contem_alergenico=bool(r.contem_alergenico),
                              quantity_kg=float(r.quantidade_kg), quantity_original=float(r.quantidade), quantity_unit=r.unidade, validity_days=int(r.dias_ate_validade),
                              expires_at=created + dt.timedelta(hours=float(r.horas_ate_validade)), validity_source="SIMULADOR", pickup_days_mask=int(r.dias_retirada_mask),
                              pickup_start_h=float(r.janela_retirada_inicio_h), pickup_end_h=float(r.janela_retirada_fim_h), load_minutes=int(r.tempo_carga_min),
                              fields={"origem": "SIMULATOR_IMPORT"}, created_at=created, imported_at=now, **_trace(r)))
            irows.append(dict(donation_id=did, categoria=r.categoria, produto=r.produto, product_name_origin=r.product_name_origin, quantity=float(r.quantidade), unit=r.unidade,
                              quantity_kg=float(r.quantidade_kg), **_trace(r)))
        out["donations"] = _bulk(session, m.Donation, drows)
        out["donation_items"] = _bulk(session, m.DonationItem, irows)
    else:
        out["donations"] = out["donation_items"] = 0
    return out


def import_all(session: Session, sim_tag: str | None = "main", with_lots: bool = True) -> dict[str, Any]:
    rep: dict[str, Any] = {}
    rep["sources"] = import_public_sources(session)
    rep["territory"] = import_municipalities(session)
    rep["food_categories"] = import_food_categories(session)
    rep["organizations"] = import_organizations(session)
    session.commit()
    if sim_tag:
        rep["simulated"] = import_simulated(session, sim_tag, with_lots)
        session.commit()
    return rep
