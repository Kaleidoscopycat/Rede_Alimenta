"""Dashboard do ADMIN: agregações em SQL (nunca tabelas inteiras), com filtros, limites e paginação.

* Perfil: SOMENTE ADMIN. Cada chamada grava `admin.access` em audit_logs (recurso `stats.<tela>`, com os parâmetros de consulta; nunca o token).
* Origem: toda linha vem rotulada (PÚBLICO / SIMULADO / MEDIDO); origens diferentes nunca são somadas num mesmo número.
* Premissa de projeto: refeições = kg ÷ ASSUMPTIONS.kg_per_meal (padrão 0,4; configurável por MEAL_KG_PER_MEAL) — premissa da equipe, não dado de fonte pública.
* "Kg salvos" NÃO é usado como rótulo: mostramos "kg ofertados" (lotes de doação) e "kg de doações coletadas" (match COLLECTED), cada um com seu selo de origem."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.orm import Session, aliased

from api import ai_info, security_reports
from api.auth import get_db, require_roles
from api.schemas import Categoria
from api.schemas_stats import (AiOut, ContagemRot, DadosPublicosOut, DoacaoBloco, DoacoesMatchesOut, DoadoresBloco, DoadoresOut, DoadorLinha, FontePublica,
                               IaResumo, LatenciaBloco, MapaOut, MatchBloco, OrganizacoesOut, OrgLinha, OverviewOut, ParadaRota, PontoMunicipio, PontoOng, Premissa, RefeicoesRegiaoOut,
                               RegiaoRow, RotaMapa, SecurityOut, SegurancaResumo, SerieMes, StrategiesIn, TempoMatchBloco, TerritorialOut, TerritorialRow, CatalogoPublico, selo)
from api.state import STATE
from core.settings import ASSUMPTIONS, IS_PRODUCTION, SETTINGS, TZ
from database import models as m

router = APIRouter(prefix="/api/v1/admin/stats", tags=["dashboard (ADMIN)"])
ORIGENS = ("SIMULATED", "USER_ENTERED")
MSG_SEM_REAL = "Nenhuma doação real registrada."
ROTULO_SIM = "Simulação: doadores, lotes e desfechos vêm do simulador documentado (data_origin=SIMULATED); não representam o mundo real."
PREMISSA = Premissa(kg_por_refeicao=ASSUMPTIONS.kg_per_meal, descricao=f"Premissa da equipe: 1 refeição = {ASSUMPTIONS.kg_per_meal:g} kg (refeições = kg ÷ {ASSUMPTIONS.kg_per_meal:g}). Não é dado de fonte pública.")
audit_dep = lambda name: require_roles("ADMIN", audit_admin=f"stats.{name}")  # noqa: E731


# ------------------------------------------------------------------------------------------------ filtros comuns
@dataclass
class Filters:
    uf: Optional[str] = None
    municipio_ibge: Optional[int] = None
    tipo_ong: Optional[str] = None
    tipo_doador: Optional[str] = None
    categoria: Optional[str] = None
    origem: Optional[str] = None
    inicio: Optional[dt.date] = None
    fim: Optional[dt.date] = None

    def as_dict(self) -> dict[str, Any]:
        return {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in self.__dict__.items() if v is not None}


def filters(uf: Optional[str] = Query(None, min_length=2, max_length=2, pattern="^[A-Za-z]{2}$"), municipio_ibge: Optional[int] = Query(None, ge=1_000_000, le=5_999_999),
            tipo_ong: Optional[str] = Query(None, max_length=30, pattern="^[A-Z_]+$"), tipo_doador: Optional[str] = Query(None, max_length=40, pattern="^[A-Z_]+$"),
            categoria: Optional[Categoria] = None, origem: Optional[Literal["PUBLIC", "SIMULATED", "USER_ENTERED"]] = None,
            inicio: Optional[dt.date] = None, fim: Optional[dt.date] = None) -> Filters:
    if inicio and fim and inicio > fim:
        raise HTTPException(422, "período inválido: início depois do fim")
    return Filters(uf=uf.upper() if uf else None, municipio_ibge=municipio_ibge, tipo_ong=tipo_ong, tipo_doador=tipo_doador, categoria=categoria, origem=origem, inicio=inicio, fim=fim)


def _start(d: dt.date) -> dt.datetime:
    return dt.datetime.combine(d, dt.time(0, 0), tzinfo=TZ)


def don_where(f: Filters) -> list:
    """Condições sobre Donation + Donor + Municipality (doações e, via junção, matches)."""
    c: list = []
    if f.uf:
        c.append(m.Municipality.uf == f.uf)
    if f.municipio_ibge:
        c.append(m.Donor.municipio_ibge == f.municipio_ibge)
    if f.tipo_doador:
        c.append(m.Donor.donor_type == f.tipo_doador)
    if f.categoria:
        c.append(or_(m.Donation.categoria == f.categoria, m.Donation.categories.any(f.categoria)))
    if f.origem:
        c.append(m.Donation.data_origin == f.origem)
    if f.inicio:
        c.append(m.Donation.created_at >= _start(f.inicio))
    if f.fim:
        c.append(m.Donation.created_at < _start(f.fim) + dt.timedelta(days=1))
    return c


def donor_where(f: Filters) -> list:
    c: list = []
    if f.uf:
        c.append(m.Municipality.uf == f.uf)
    if f.municipio_ibge:
        c.append(m.Donor.municipio_ibge == f.municipio_ibge)
    if f.tipo_doador:
        c.append(m.Donor.donor_type == f.tipo_doador)
    if f.origem:
        c.append(m.Donor.data_origin == f.origem)
    return c


def org_where(f: Filters) -> list:
    c: list = []
    if f.uf:
        c.append(m.Organization.uf == f.uf)
    if f.municipio_ibge:
        c.append(m.Organization.municipio_ibge == f.municipio_ibge)
    if f.tipo_ong:
        c.append(m.Organization.ong_tipo == f.tipo_ong)
    if f.origem and f.origem != "PUBLIC":
        c.append(False)  # ONGs catalogadas são sempre PUBLIC
    return c


def _dj(q):
    """Doação ⟶ doador ⟶ município."""
    return q.select_from(m.Donation).join(m.Donor, m.Donor.id == m.Donation.donor_id).join(m.Municipality, m.Municipality.ibge_code == m.Donor.municipio_ibge)


def _mj(q):
    """Match ⟶ doação ⟶ doador ⟶ município."""
    return q.select_from(m.Match).join(m.Donation, m.Donation.id == m.Match.donation_id).join(m.Donor, m.Donor.id == m.Donation.donor_id).join(
        m.Municipality, m.Municipality.ibge_code == m.Donor.municipio_ibge)


def _r(x: Any, nd: int = 2) -> Optional[float]:
    return None if x is None else round(float(x), nd)


def _meals(kg: float) -> float:
    return round(float(ASSUMPTIONS.kg_to_meals(kg) or 0.0), 1)


def _kg_blocks(rows: dict[str, tuple[int, float]], titulo: str, legenda: str) -> list[DoacaoBloco]:
    out = []
    for o in ORIGENS:  # sempre as duas origens, mesmo zeradas: a ausência de doação real fica explícita
        n, kg = rows.get(o, (0, 0.0))
        out.append(DoacaoBloco(data_origin=o, selo=selo(o), n_doacoes=n, kg=round(kg, 1), refeicoes_estimadas=_meals(kg), titulo=f"{titulo} — {'Simulação' if o == 'SIMULATED' else 'Medido (entrada real)'}",
                               legenda=legenda + (" " + ROTULO_SIM if o == "SIMULATED" else "")))
    return out


def _has_real(db: Session) -> bool:
    return bool(db.scalar(select(func.count()).select_from(m.Donation).where(m.Donation.data_origin == "USER_ENTERED")))


# ------------------------------------------------------------------------------------------------ consultas reutilizadas
def q_kg_ofertado(db: Session, f: Filters) -> dict[str, tuple[int, float]]:
    q = _dj(select(m.Donation.data_origin, func.count(), func.coalesce(func.sum(m.Donation.quantity_kg), 0.0))).where(*don_where(f)).group_by(m.Donation.data_origin)
    return {o: (int(n), float(kg)) for o, n, kg in db.execute(q)}


def q_kg_coletado(db: Session, f: Filters) -> dict[str, tuple[int, float]]:
    q = _mj(select(m.Match.data_origin, func.count(distinct(m.Donation.id)), func.coalesce(func.sum(m.Donation.quantity_kg), 0.0))).where(m.Match.status == "COLLECTED", *don_where(f)).group_by(m.Match.data_origin)
    return {o: (int(n), float(kg)) for o, n, kg in db.execute(q)}


def q_matches(db: Session, f: Filters) -> list[MatchBloco]:
    base = _mj(select(m.Match.data_origin, func.count(distinct(m.Match.id)))).where(*don_where(f)).group_by(m.Match.data_origin)
    n_matches = {o: int(n) for o, n in db.execute(base)}
    st = _mj(select(m.Match.data_origin, func.count())).where(m.Match.status == "COLLECTED", *don_where(f)).group_by(m.Match.data_origin)
    coletadas = {o: int(n) for o, n in db.execute(st)}
    ev = (select(m.MatchEvent.data_origin, m.MatchEvent.event_type, func.count()).select_from(m.MatchEvent).join(m.Match, m.Match.id == m.MatchEvent.match_id)
          .join(m.Donation, m.Donation.id == m.Match.donation_id).join(m.Donor, m.Donor.id == m.Donation.donor_id).join(m.Municipality, m.Municipality.ibge_code == m.Donor.municipio_ibge)
          .where(*don_where(f)).group_by(m.MatchEvent.data_origin, m.MatchEvent.event_type))
    cnt: dict[str, dict[str, int]] = {o: {} for o in ORIGENS}
    for o, t, n in db.execute(ev):
        cnt.setdefault(o, {})[t] = int(n)
    out = []
    for o in ORIGENS:
        c = cnt.get(o, {})
        acc, dec, exp = c.get("ACCEPTED", 0), c.get("DECLINED", 0), c.get("EXPIRED", 0)
        out.append(MatchBloco(data_origin=o, selo=selo(o), n_matches=n_matches.get(o, 0), propostas=c.get("PROPOSED", 0), aceitas=acc, recusadas=dec, expiradas=exp, coletadas=coletadas.get(o, 0),
                              taxa_aceite=round(acc / (acc + dec + exp), 4) if (acc + dec + exp) else None))
    return out


def q_tempo_match(db: Session, f: Filters) -> list[TempoMatchBloco]:
    """Tempos a partir dos timestamps de match_events e da data de registro da doação (somente doações cadastradas pela API; o histórico importado não tem fluxo de match)."""
    fp = select(m.MatchEvent.match_id.label("mid"), func.min(m.MatchEvent.at).label("at")).where(m.MatchEvent.event_type == "PROPOSED").group_by(m.MatchEvent.match_id).subquery()
    fa = select(m.MatchEvent.match_id.label("mid"), func.min(m.MatchEvent.at).label("at")).where(m.MatchEvent.event_type == "ACCEPTED").group_by(m.MatchEvent.match_id).subquery()
    ep = lambda col, ref: func.extract("epoch", col - ref)  # noqa: E731
    q = (_mj(select(m.Match.data_origin, func.count(distinct(m.Match.id)), func.avg(ep(fp.c.at, m.Donation.created_at)), func.avg(ep(fa.c.at, m.Donation.created_at))))
         .join(fp, fp.c.mid == m.Match.id, isouter=True).join(fa, fa.c.mid == m.Match.id, isouter=True)
         .where(m.Donation.entry_channel == "API", *don_where(f)).group_by(m.Match.data_origin))
    base = {o: (int(n), a, b) for o, n, a, b in db.execute(q)}
    ev = select(m.MatchEvent.match_id.label("mid"), m.MatchEvent.event_type.label("et"), m.MatchEvent.at.label("at"), m.MatchEvent.data_origin.label("o"),
                func.lag(m.MatchEvent.event_type).over(partition_by=m.MatchEvent.match_id, order_by=m.MatchEvent.id).label("pt"),
                func.lag(m.MatchEvent.at).over(partition_by=m.MatchEvent.match_id, order_by=m.MatchEvent.id).label("pat")).subquery()
    qr = (select(ev.c.o, func.avg(func.extract("epoch", ev.c.at - ev.c.pat))).select_from(ev).join(m.Match, m.Match.id == ev.c.mid).join(m.Donation, m.Donation.id == m.Match.donation_id)
          .join(m.Donor, m.Donor.id == m.Donation.donor_id).join(m.Municipality, m.Municipality.ibge_code == m.Donor.municipio_ibge)
          .where(ev.c.et.in_(("ACCEPTED", "DECLINED")), ev.c.pt == "PROPOSED", m.Donation.entry_channel == "API", *don_where(f)).group_by(ev.c.o))
    resp = {o: a for o, a in db.execute(qr)}
    txt = {"SIMULATED": "execuções de demonstração sobre doações simuladas (as respostas das ONGs vêm de contas de teste); NÃO é o tempo real de ONGs.",
           "USER_ENTERED": "uso real registrado pela plataforma (entrada real)."}
    out = []
    for o in ORIGENS:
        n, a, b = base.get(o, (0, None, None))
        out.append(TempoMatchBloco(data_origin=o, selo=selo(o), n_matches=n, registro_ate_primeira_proposta_s=_r(a, 3), proposta_ate_resposta_s=_r(resp.get(o), 3), registro_ate_aceite_s=_r(b, 3), origem_texto=txt[o]))
    return out


def q_latencia(db: Session, f: Filters) -> list[LatenciaBloco]:
    tot = m.Match.latency_ms["total_ms"].as_float()
    q = (_mj(select(m.Match.data_origin, func.count(), func.avg(tot), func.percentile_cont(0.5).within_group(tot), func.percentile_cont(0.95).within_group(tot)))
         .where(tot.is_not(None), *don_where(f)).group_by(m.Match.data_origin))
    got = {o: (int(n), a, p5, p95) for o, n, a, p5, p95 in db.execute(q)}
    return [LatenciaBloco(data_origin=o, selo=selo(o), n=got.get(o, (0, None, None, None))[0], media_ms=_r(got.get(o, (0, None, None, None))[1]),
                          p50_ms=_r(got.get(o, (0, None, None, None))[2]), p95_ms=_r(got.get(o, (0, None, None, None))[3])) for o in ORIGENS]


def ia_resumo() -> IaResumo:
    r = ai_info.ranker_block()
    p = ai_info.parser_block()
    if not r.get("disponivel"):
        return IaResumo(disponivel=False, rotulo=ai_info.ROTULO, nota_nomes="artefatos do modelo ausentes")
    esc = next((x for x in r["tabela_comparacao"] if x["escolhido"]), {})
    b_prox = next((x for x in r["tabela_comparacao"] if x["modelo"] == "Baseline: ONG mais próxima"), {})
    b_regra = next((x for x in r["tabela_comparacao"] if x["modelo"].startswith("Baseline: regra")), {})
    acc = None
    if p.get("disponivel") and p["avaliacoes"]:
        acc = p["avaliacoes"][0].get("acc_categoria")
    return IaResumo(disponivel=True, rotulo=ai_info.ROTULO, versao=r["versao"], mrr=esc.get("mrr"), top1_hit_rate=esc.get("top1_hit_rate"), top3_hit_rate=esc.get("top3_hit_rate"),
                    mrr_baseline_ong_mais_proxima=b_prox.get("mrr"), mrr_baseline_regra=b_regra.get("mrr"), acc_categoria_parser=acc,
                    nota_nomes="O ranker NÃO tem 'acurácia': suas métricas reais são MRR, Top-1, Top-3 e NDCG@3 (ranking). 'Acurácia' existe apenas no parser de texto (categoria, perecibilidade, refrigeração), em texto simulado.")


# ------------------------------------------------------------------------------------------------ 1. Overview
@router.get("/overview", response_model=OverviewOut, summary="ADMIN: indicadores principais com selo de origem")
def overview(f: Filters = Depends(filters), db: Session = Depends(get_db), user: m.User = Depends(audit_dep("overview"))):
    org_cond = org_where(f)
    n_orgs = db.scalar(select(func.count()).select_from(m.Organization).where(*org_cond, m.Organization.ong_tipo == "OSC_ASSISTENCIA")) if not (f.origem and f.origem != "PUBLIC") else 0
    n_rbba = db.scalar(select(func.count()).select_from(m.Organization).where(*org_cond, m.Organization.ong_tipo == "BANCO_ALIMENTOS_RBBA")) if not (f.origem and f.origem != "PUBLIC") else 0
    muni = db.execute(select(func.count(distinct(m.Organization.municipio_ibge)), func.count(distinct(m.Organization.uf))).where(*org_cond)).one() if not (f.origem and f.origem != "PUBLIC") else (0, 0)
    last = select(m.PublicDatasetVersion.source_id, func.max(m.PublicDatasetVersion.ingested_at).label("mx")).group_by(m.PublicDatasetVersion.source_id).subquery()
    regs = db.scalar(select(func.coalesce(func.sum(m.PublicDatasetVersion.n_records), 0)).join(last, and_(last.c.source_id == m.PublicDatasetVersion.source_id, last.c.mx == m.PublicDatasetVersion.ingested_at)))
    n_src = db.scalar(select(func.count()).select_from(m.PublicDataSource))
    upd = db.scalar(select(func.max(m.PublicDataSource.ingested_at)))
    catalogo = CatalogoPublico(data_origin="PUBLIC", selo="PÚBLICO", ongs_catalogadas=int(n_orgs or 0) + int(n_rbba or 0), bancos_de_alimentos_rbba=int(n_rbba or 0), municipios_cobertos=int(muni[0]),
                               ufs_cobertas=int(muni[1]), registros_publicos_processados=int(regs or 0), fontes_publicas=int(n_src or 0), ultima_atualizacao_datasets=upd,
                               nota="Registros de fontes públicas (histórico oficial). Pertencem às fontes, NÃO à Rede Alimenta; as ONGs não são clientes da plataforma até o cadastro.")
    don_q = _dj(select(m.Donor.data_origin, func.count(distinct(m.Donor.id)))).where(*donor_where(f)).group_by(m.Donor.data_origin)
    n_don = {o: int(n) for o, n in db.execute(don_q)}
    doadores = [DoadoresBloco(data_origin=o, selo=selo(o), n_doadores=n_don.get(o, 0)) for o in ORIGENS]
    real = _has_real(db)
    leg_of = "Kg em lotes de doação cadastrados (potencial ofertado). NÃO é kg salvo: salvo = coletado."
    leg_co = "Kg de doações cuja coleta foi concluída (match COLLECTED)."
    sec = security_reports.compute()
    return OverviewOut(premissa=PREMISSA, catalogo=catalogo, doadores=doadores,
                       doacoes_ofertadas=_kg_blocks(q_kg_ofertado(db, f), "Kg ofertados em lotes de doação", leg_of),
                       doacoes_coletadas=_kg_blocks(q_kg_coletado(db, f), "Kg de doações coletadas", leg_co),
                       matches=q_matches(db, f), tempo_match=q_tempo_match(db, f), latencia_ranking=q_latencia(db, f), ia=ia_resumo(),
                       seguranca=SegurancaResumo(total_mitigadas_comprovadas=sec["total_mitigadas_comprovadas"], ferramentas_comprovadas=sec["ferramentas_comprovadas"], pendencias=sec["pendencias"]),
                       nenhuma_doacao_real=not real, aviso_doacao_real=None if real else MSG_SEM_REAL, filtros_aplicados=f.as_dict())


# ------------------------------------------------------------------------------------------------ 2. Doações e matches
@router.get("/donations-matches", response_model=DoacoesMatchesOut, summary="ADMIN: doações e matches Doador × ONG (série mensal, status, categorias, ciclo do match, latência)")
def donations_matches(f: Filters = Depends(filters), db: Session = Depends(get_db), user: m.User = Depends(audit_dep("donations_matches"))):
    mes = func.to_char(func.timezone("America/Sao_Paulo", m.Donation.created_at), "YYYY-MM")
    serie = _dj(select(mes, m.Donation.data_origin, func.count(), func.coalesce(func.sum(m.Donation.quantity_kg), 0.0))).where(*don_where(f)).group_by(mes, m.Donation.data_origin).order_by(mes).limit(240)
    series = [SerieMes(mes=a, data_origin=o, selo=selo(o), n_doacoes=int(n), kg=round(float(kg), 1), refeicoes_estimadas=_meals(kg)) for a, o, n, kg in db.execute(serie)]
    st = _dj(select(m.Donation.data_origin, m.Donation.status, func.count())).where(*don_where(f)).group_by(m.Donation.data_origin, m.Donation.status).order_by(m.Donation.data_origin, m.Donation.status)
    por_status = [ContagemRot(data_origin=o, selo=selo(o), chave=s, n=int(n)) for o, s, n in db.execute(st)]
    cat = _dj(select(m.Donation.data_origin, m.Donation.categoria, func.count(), func.coalesce(func.sum(m.Donation.quantity_kg), 0.0))).where(*don_where(f), m.Donation.categoria.is_not(None)) \
        .group_by(m.Donation.data_origin, m.Donation.categoria).order_by(func.sum(m.Donation.quantity_kg).desc()).limit(60)
    por_cat = [ContagemRot(data_origin=o, selo=selo(o), chave=c, n=int(n), kg=round(float(kg), 1)) for o, c, n, kg in db.execute(cat)]
    ms = _mj(select(m.Match.data_origin, m.Match.status, func.count())).where(*don_where(f)).group_by(m.Match.data_origin, m.Match.status)
    m_status = [ContagemRot(data_origin=o, selo=selo(o), chave=s, n=int(n)) for o, s, n in db.execute(ms)]
    ev = (select(m.MatchEvent.data_origin, m.MatchEvent.event_type, func.count()).select_from(m.MatchEvent).join(m.Match, m.Match.id == m.MatchEvent.match_id)
          .join(m.Donation, m.Donation.id == m.Match.donation_id).join(m.Donor, m.Donor.id == m.Donation.donor_id).join(m.Municipality, m.Municipality.ibge_code == m.Donor.municipio_ibge)
          .where(*don_where(f)).group_by(m.MatchEvent.data_origin, m.MatchEvent.event_type))
    ciclo = [ContagemRot(data_origin=o, selo=selo(o), chave=t, n=int(n)) for o, t, n in db.execute(ev)]
    return DoacoesMatchesOut(titulo="Doações e matches Doador × ONG", legenda="Doações e matches por origem do dado. " + ROTULO_SIM, serie_mensal=series, por_status=por_status, por_categoria=por_cat,
                             matches_por_status=m_status, ciclo_do_match=ciclo, latencia_ranking=q_latencia(db, f), premissa=PREMISSA, nenhuma_doacao_real=not _has_real(db))


# ------------------------------------------------------------------------------------------------ 3. Refeições por região
@router.get("/meals-by-region", response_model=RefeicoesRegiaoOut, summary="ADMIN: refeições estimadas por região (kg ÷ premissa), por origem")
def meals_by_region(nivel: Literal["macro", "uf", "municipio"] = "uf", base: Literal["ofertado", "coletado"] = "ofertado", limit: int = Query(60, ge=1, le=200),
                    f: Filters = Depends(filters), db: Session = Depends(get_db), user: m.User = Depends(audit_dep("meals_by_region"))):
    cols = {"macro": (m.Municipality.region,), "uf": (m.Municipality.region, m.Municipality.uf), "municipio": (m.Municipality.region, m.Municipality.uf, m.Municipality.ibge_code, m.Municipality.name)}[nivel]
    kg = func.coalesce(func.sum(m.Donation.quantity_kg), 0.0)
    if base == "ofertado":
        q = _dj(select(*cols, m.Donation.data_origin, func.count(distinct(m.Donation.id)), kg)).where(*don_where(f))
        org_col = m.Donation.data_origin
    else:
        q = _mj(select(*cols, m.Match.data_origin, func.count(distinct(m.Donation.id)), kg)).where(m.Match.status == "COLLECTED", *don_where(f))
        org_col = m.Match.data_origin
    q = q.group_by(*cols, org_col).order_by(kg.desc()).limit(limit)
    linhas = []
    for r in db.execute(q):
        reg, uf, ibge, nome = (r[0], r[1] if nivel != "macro" else None, r[2] if nivel == "municipio" else None, r[3] if nivel == "municipio" else None)
        o, n, k = r[-3], r[-2], r[-1]
        linhas.append(RegiaoRow(regiao=reg if nivel == "macro" else (uf or reg), uf=uf, municipio_ibge=ibge, nome=nome, data_origin=o, selo=selo(o), n_doacoes=int(n), kg=round(float(k), 1),
                                refeicoes_estimadas=_meals(k)))
    what = "kg ofertados em lotes de doação" if base == "ofertado" else "kg de doações coletadas"
    return RefeicoesRegiaoOut(titulo="Refeições estimadas por região — Simulação" if any(x.data_origin == "SIMULATED" for x in linhas) or not linhas else "Refeições estimadas por região",
                              legenda=f"Refeições estimadas = {what} ÷ {ASSUMPTIONS.kg_per_meal:g} (premissa da equipe). " + ROTULO_SIM, nivel=nivel, base=base, premissa=PREMISSA, linhas=linhas,
                              nenhuma_doacao_real=not _has_real(db))


# ------------------------------------------------------------------------------------------------ 4. Mapa
@router.get("/map", response_model=MapaOut, summary="ADMIN: camadas do mapa (ONGs, doadores, densidade de doações, rotas planejadas) com selo de origem")
def map_layers(max_pontos: int = Query(1500, ge=0, le=5000), max_rotas: int = Query(30, ge=0, le=100), f: Filters = Depends(filters), db: Session = Depends(get_db),
               user: m.User = Depends(audit_dep("map"))):
    M = m.Municipality
    ongs_muni: list[PontoMunicipio] = []
    pontos: list[PontoOng] = []
    trunc = False
    if not (f.origem and f.origem != "PUBLIC"):
        q = (select(M.ibge_code, M.name, M.uf, M.lat, M.lon, func.count()).select_from(m.Organization).join(M, M.ibge_code == m.Organization.municipio_ibge)
             .where(*org_where(f), M.lat.is_not(None)).group_by(M.ibge_code, M.name, M.uf, M.lat, M.lon).order_by(func.count().desc()).limit(6000))
        ongs_muni = [PontoMunicipio(municipio_ibge=a, nome=b, uf=c, lat=d, lon=e, n=int(n), data_origin="PUBLIC", selo="PÚBLICO") for a, b, c, d, e, n in db.execute(q)]
        total = db.scalar(select(func.count()).select_from(m.Organization).where(*org_where(f))) or 0
        trunc = total > max_pontos
        if max_pontos:
            qp = (select(m.Organization.ong_id, m.Organization.ong_tipo, m.Organization.uf, m.OrganizationLocation.lat, m.OrganizationLocation.lon, m.OrganizationLocation.location_precision)
                  .select_from(m.Organization).join(m.OrganizationLocation, m.OrganizationLocation.organization_id == m.Organization.id)
                  .where(*org_where(f), m.OrganizationLocation.lat.is_not(None)).order_by((m.OrganizationLocation.location_precision != "EXACT"), m.Organization.ong_id).limit(max_pontos))
            pontos = [PontoOng(ong_id=a, ong_tipo=b, uf=c, lat=d, lon=e, location_precision=p) for a, b, c, d, e, p in db.execute(qp)]
    qd = (select(M.ibge_code, M.name, M.uf, M.lat, M.lon, m.Donor.data_origin, func.count()).select_from(m.Donor).join(M, M.ibge_code == m.Donor.municipio_ibge)
          .where(*donor_where(f), M.lat.is_not(None)).group_by(M.ibge_code, M.name, M.uf, M.lat, M.lon, m.Donor.data_origin).limit(6000))
    doadores = [PontoMunicipio(municipio_ibge=a, nome=b, uf=c, lat=d, lon=e, n=int(n), data_origin=o, selo=selo(o)) for a, b, c, d, e, o, n in db.execute(qd)]
    kg = func.coalesce(func.sum(m.Donation.quantity_kg), 0.0)
    qk = (_dj(select(M.ibge_code, M.name, M.uf, M.lat, M.lon, m.Donation.data_origin, func.count(), kg)).where(*don_where(f), M.lat.is_not(None))
          .group_by(M.ibge_code, M.name, M.uf, M.lat, M.lon, m.Donation.data_origin).order_by(kg.desc()).limit(6000))
    doacoes = [PontoMunicipio(municipio_ibge=a, nome=b, uf=c, lat=d, lon=e, n=int(n), kg=round(float(k), 1), refeicoes_estimadas=_meals(k), data_origin=o, selo=selo(o)) for a, b, c, d, e, o, n, k in db.execute(qk)]
    rotas = _rotas(db, f, max_rotas)
    return MapaOut(titulo="Mapa de ONGs, doadores e doações", legenda=("ONGs: registros públicos (PÚBLICO), posição EXATA ou centroide do município. Doadores e doações: SIMULADOS — localização simulada derivada do centroide de um município REAL. "
                                                                    "Rotas: planejadas pelo módulo de roteirização, com o selo da origem das paradas."),
                   ongs_por_municipio=ongs_muni, ongs_pontos=pontos, ongs_pontos_truncado=trunc, doadores_por_municipio=doadores, doacoes_por_municipio=doacoes, rotas=rotas,
                   aviso_localizacao=("Distâncias e rotas usam centroide de município quando a posição exata é desconhecida e são estimadas em LINHA RETA × fator de desvio ÷ velocidade — não são rotas viárias."),
                   sem_mapa_base="O mapa não usa camada de fundo de terceiros (sem chave de API, sem serviço externo de tiles): apenas os pontos e rotas.")


def _rotas(db: Session, f: Filters, limit: int) -> list[RotaMapa]:
    if limit == 0:
        return []
    q = select(m.Route, m.Organization.ong_id).join(m.Organization, m.Organization.id == m.Route.organization_id).where(m.Route.is_primary)
    if f.origem:
        q = q.where(m.Route.data_origin == f.origem)
    if f.uf:
        q = q.where(m.Organization.uf == f.uf)
    if f.municipio_ibge:
        q = q.where(m.Organization.municipio_ibge == f.municipio_ibge)
    if f.inicio:
        q = q.where(m.Route.created_at >= _start(f.inicio))
    if f.fim:
        q = q.where(m.Route.created_at < _start(f.fim) + dt.timedelta(days=1))
    out = []
    for r, ong in db.execute(q.order_by(m.Route.created_at.desc()).limit(limit)):
        stops = list(db.execute(select(m.RouteStop, m.Donor.external_id).join(m.Donor, m.Donor.id == m.RouteStop.donor_id, isouter=True).where(m.RouteStop.route_id == r.id).order_by(m.RouteStop.seq)))
        paradas = [ParadaRota(seq=s.seq, tipo=s.stop_type, lat=s.lat, lon=s.lon, location_precision=s.location_precision, doador=ext, chegada_planejada=s.planned_arrival_at) for s, ext in stops]
        aprox = any(p.location_precision != "EXACT" for p in paradas)
        aviso = ("Distância estimada em linha reta × desvio; " + ("alguma parada usa centroide de município (posição aproximada)." if aprox else "paradas com posição exata.")) if paradas else None
        out.append(RotaMapa(data_origin=r.data_origin, selo=selo(r.data_origin), id=str(r.id), ong_id=ong, algoritmo=r.algorithm, status=r.status, total_km_est=_r(r.total_km_est), total_minutos_est=r.total_minutes_est,
                            distancia_base=r.distance_basis, paradas=paradas, aviso_distancia=aviso))
    return out


# ------------------------------------------------------------------------------------------------ 5. Organizações
@router.get("/organizations", response_model=OrganizacoesOut, summary="ADMIN: ONGs e bancos de alimentos catalogados (fontes públicas), resumo e tabela paginada")
def organizations(limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0, le=1_000_000), f: Filters = Depends(filters), db: Session = Depends(get_db),
                  user: m.User = Depends(audit_dep("organizations"))):
    O, L, P, M = m.Organization, m.OrganizationLocation, m.OrganizationProfile, m.Municipality
    w = org_where(f)

    def cnt(col, label_prefix: str = "") -> list[ContagemRot]:
        q = select(col, func.count()).select_from(O).join(L, L.organization_id == O.id).outerjoin(P, P.organization_id == O.id).where(*w).group_by(col).order_by(func.count().desc()).limit(40)
        return [ContagemRot(data_origin="PUBLIC", selo="PÚBLICO", chave=str(k) if k is not None else "—", n=int(n)) for k, n in db.execute(q)]
    total = int(db.scalar(select(func.count()).select_from(O).where(*w)) or 0)
    prof_q = select(P.data_origin, func.count()).select_from(O).join(P, P.organization_id == O.id).where(*w).group_by(P.data_origin)
    perfil = [ContagemRot(data_origin=o, selo=selo(o), chave="perfil declarado (capacidade, horários, refrigeração)", n=int(n)) for o, n in db.execute(prof_q)]
    q = (select(O.ong_id, O.ong_tipo, O.uf, O.municipio_ibge, M.name, L.location_precision, O.platform_status, O.license_review_status, P.data_origin, P.capacity_max_kg_day, P.cold_chamber, P.has_fleet)
         .select_from(O).join(L, L.organization_id == O.id).outerjoin(P, P.organization_id == O.id).outerjoin(M, M.ibge_code == O.municipio_ibge).where(*w).order_by(O.ong_id).limit(limit).offset(offset))
    linhas = [OrgLinha(ong_id=a, ong_tipo=b, uf=c, municipio_ibge=d, municipio=e, location_precision=g, platform_status=h, licenca=i, perfil_origin=j, capacidade_max_kg_dia=_r(k, 1), camara_fria=cf, tem_frota=fl)
              for a, b, c, d, e, g, h, i, j, k, cf, fl in db.execute(q)]
    return OrganizacoesOut(titulo="Organizações (ONGs e bancos de alimentos)", legenda=("Registros de fontes públicas (PÚBLICO), por pseudônimo. Capacidade, horários e refrigeração são DECLARADOS SIMULADOS enquanto não houver cadastro real. "
                                                                                         "As organizações NÃO são clientes da plataforma até o cadastro."),
                           total=total, por_tipo=cnt(O.ong_tipo), por_uf=cnt(O.uf), por_precisao_localizacao=cnt(L.location_precision), por_status_plataforma=cnt(O.platform_status),
                           perfil_declarado=perfil, linhas=linhas, limit=limit, offset=offset)


# ------------------------------------------------------------------------------------------------ 6. Doadores
@router.get("/donors", response_model=DoadoresOut, summary="ADMIN: doadores (pessoas jurídicas), resumo e tabela paginada, com selo de origem")
def donors(limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0, le=1_000_000), f: Filters = Depends(filters), db: Session = Depends(get_db), user: m.User = Depends(audit_dep("donors"))):
    D, M = m.Donor, m.Municipality
    w = donor_where(f)

    def cnt(col) -> list[ContagemRot]:
        q = select(D.data_origin, col, func.count()).select_from(D).join(M, M.ibge_code == D.municipio_ibge).where(*w).group_by(D.data_origin, col).order_by(D.data_origin, func.count().desc()).limit(80)
        return [ContagemRot(data_origin=o, selo=selo(o), chave=str(k) if k is not None else "—", n=int(n)) for o, k, n in db.execute(q)]
    tot = db.execute(select(D.data_origin, func.count()).select_from(D).join(M, M.ibge_code == D.municipio_ibge).where(*w).group_by(D.data_origin)).all()
    totals = {o: int(n) for o, n in tot}
    total = [ContagemRot(data_origin=o, selo=selo(o), chave="doadores", n=totals.get(o, 0)) for o in ORIGENS]
    sub = select(m.Donation.donor_id.label("did"), func.count().label("n"), func.coalesce(func.sum(m.Donation.quantity_kg), 0.0).label("kg")).group_by(m.Donation.donor_id).subquery()
    q = (select(D.id, D.external_id, D.donor_type, D.donor_size, M.uf, D.municipio_ibge, M.name, D.data_origin, func.coalesce(sub.c.n, 0), func.coalesce(sub.c.kg, 0.0)).select_from(D)
         .join(M, M.ibge_code == D.municipio_ibge).outerjoin(sub, sub.c.did == D.id).where(*w).order_by(D.data_origin, D.external_id, D.id).limit(limit).offset(offset))
    linhas = [DoadorLinha(donor_id=str(a), external_id=b, donor_type=c, donor_size=d, uf=e, municipio_ibge=g, municipio=h, data_origin=o, selo=selo(o), n_doacoes=int(n), kg=round(float(k), 1))
              for a, b, c, d, e, g, h, o, n, k in db.execute(q)]
    return DoadoresOut(titulo="Doadores", legenda="Doadores são pessoas jurídicas. SIMULADOS: perfil operacional gerado pelo simulador, em município REAL, sem nome nem CNPJ. MEDIDO: cadastrado na plataforma. " + ROTULO_SIM,
                       total=total, por_tipo=cnt(D.donor_type), por_porte=cnt(D.donor_size), linhas=linhas, limit=limit, offset=offset, nenhuma_doacao_real=not _has_real(db))


# ------------------------------------------------------------------------------------------------ 7. Dados públicos
@router.get("/public-data", response_model=DadosPublicosOut, summary="ADMIN: fontes públicas, versões, registros processados e situação de licença")
def public_data(db: Session = Depends(get_db), user: m.User = Depends(audit_dep("public_data"))):
    last = select(m.PublicDatasetVersion.source_id, func.max(m.PublicDatasetVersion.ingested_at).label("mx")).group_by(m.PublicDatasetVersion.source_id).subquery()
    ver = {r.source_id: r for r in db.scalars(select(m.PublicDatasetVersion).join(last, and_(last.c.source_id == m.PublicDatasetVersion.source_id, last.c.mx == m.PublicDatasetVersion.ingested_at)))}
    fontes = []
    for s in db.scalars(select(m.PublicDataSource).order_by(m.PublicDataSource.id)):
        v = ver.get(s.id)
        fontes.append(FontePublica(id=s.id, nome=s.name, organizacao=s.organization, url=s.url, licenca=s.license_status, revisao=s.review_status, uso_comercial=s.commercial_use,
                                   liberada_para_publicacao=bool(s.publication_cleared), n_registros=v.n_records if v else None, versao=v.version_label if v else None, ingerida_em=s.ingested_at,
                                   atualizada_na_fonte=s.source_updated_at))
    ind = [{"codigo": c, "unidade": u, "periodo": p, "n_municipios": int(n), "data_origin": "PUBLIC", "selo": "PÚBLICO"}
           for c, u, p, n in db.execute(select(m.PublicIndicator.code, m.PublicIndicator.unit, m.PublicIndicator.reference_period, func.count()).group_by(m.PublicIndicator.code, m.PublicIndicator.unit,
                                                                                                                                              m.PublicIndicator.reference_period).order_by(m.PublicIndicator.code))]
    return DadosPublicosOut(titulo="Dados públicos", legenda="Fontes oficiais usadas como dado REAL (PÚBLICO). O histórico (ex.: PAA) pertence à fonte, não à Rede Alimenta.", fontes=fontes,
                            registros_processados=sum(x.n_registros or 0 for x in fontes), ultima_atualizacao=max((x.ingerida_em for x in fontes if x.ingerida_em), default=None), indicadores_por_codigo=ind,
                            aviso_licenca=("Dados demonstrativos — uso exclusivamente acadêmico, sem fins comerciais. Licenças não confirmadas estão listadas como tal; nenhuma fonte está liberada para publicação comercial "
                                           "(ver docs/data/DATA_LICENSES.md e PENDING_LICENSE_CONFIRMATIONS.md)."))


# ------------------------------------------------------------------------------------------------ 8. Indicadores territoriais
@router.get("/territorial", response_model=TerritorialOut, summary="ADMIN: indicadores territoriais públicos por UF ou município")
def territorial(codigo: str = Query("populacao_2026", max_length=60, pattern="^[a-z0-9_]+$"), nivel: Literal["uf", "municipio"] = "uf", limit: int = Query(40, ge=1, le=200),
                f: Filters = Depends(filters), db: Session = Depends(get_db), user: m.User = Depends(audit_dep("territorial"))):
    disp = [{"codigo": c, "unidade": u, "periodo": p} for c, u, p in db.execute(select(m.PublicIndicator.code, m.PublicIndicator.unit, m.PublicIndicator.reference_period).group_by(
        m.PublicIndicator.code, m.PublicIndicator.unit, m.PublicIndicator.reference_period).order_by(m.PublicIndicator.code))]
    cur = next((d for d in disp if d["codigo"] == codigo), None)
    if cur is None:
        raise HTTPException(422, "indicador desconhecido; use um dos códigos disponíveis")
    I, P, M = m.PublicIndicator, aliased(m.PublicIndicator), m.Municipality
    w = []
    if f.uf:
        w.append(M.uf == f.uf)
    if f.municipio_ibge:
        w.append(M.ibge_code == f.municipio_ibge)
    pop = func.sum(P.value)
    val = func.sum(I.value)
    if nivel == "uf":
        q = (select(M.uf, val, pop).select_from(I).join(M, M.ibge_code == I.municipio_ibge).join(P, and_(P.municipio_ibge == I.municipio_ibge, P.code == "populacao_2026"), isouter=True)
             .where(I.code == codigo, *w).group_by(M.uf).order_by(val.desc()).limit(limit))
        linhas = [TerritorialRow(chave=uf, uf=uf, valor=round(float(v), 2), populacao=_r(p, 0), por_100mil_habitantes=_r(float(v) / float(p) * 100000, 2) if p else None) for uf, v, p in db.execute(q)]
    else:
        q = (select(M.ibge_code, M.name, M.uf, I.value, P.value).select_from(I).join(M, M.ibge_code == I.municipio_ibge).join(P, and_(P.municipio_ibge == I.municipio_ibge, P.code == "populacao_2026"), isouter=True)
             .where(I.code == codigo, *w).order_by(I.value.desc()).limit(limit))
        linhas = [TerritorialRow(chave=str(a), nome=b, uf=c, valor=round(float(v), 2), populacao=_r(p, 0), por_100mil_habitantes=_r(float(v) / float(p) * 100000, 2) if p else None) for a, b, c, v, p in db.execute(q)]
    return TerritorialOut(titulo=f"Indicadores territoriais — {codigo}", legenda="Indicadores de fontes públicas por território (PÚBLICO). Contexto regional apenas; a plataforma não trata beneficiários finais.", codigo=codigo,
                          unidade=cur["unidade"], periodo_referencia=cur["periodo"], nivel=nivel, codigos_disponiveis=disp, linhas=linhas,
                          nota="Valores por UF são a SOMA dos municípios; 'por 100 mil habitantes' é derivado (valor ÷ população 2026 × 100 000). Para paa_adesao a soma é o número de municípios com adesão.")


# ------------------------------------------------------------------------------------------------ 9. IA
@router.get("/ai", response_model=AiOut, summary="ADMIN: IA — versão, métricas reais (com os nomes reais), baselines, datasets, importância, limitações")
def ai(db: Session = Depends(get_db), user: m.User = Depends(audit_dep("ai"))):
    n_total, n_mixed = db.execute(select(func.count(), func.count().filter(m.Donation.is_mixed_batch))
                                  .where(m.Donation.entry_channel == "API")).one()
    mixed = {"n_total": int(n_total), "n_mistos": int(n_mixed), "parcela": (n_mixed / n_total) if n_total else None,
             "escopo": "doações cadastradas pela plataforma (canal API); o histórico simulado importado não é lote misto"}
    dvs = [r[0] for r in db.execute(select(m.Donor.dataset_version).where(m.Donor.data_origin == "SIMULATED").distinct().limit(5)) if r[0]]
    r = ai_info.ranker_block()
    datasets = [{"nome": "Atributos de ONGs, municípios e indicadores", "data_origin": "PUBLIC", "selo": "PÚBLICO", "versao": (r.get("datasets") or {}).get("real")},
                {"nome": "Doadores, lotes, desfechos e perfil declarado das ONGs (simulador documentado)", "data_origin": "SIMULATED", "selo": "SIMULADO",
                 "versao_treino": (r.get("datasets") or {}).get("simulado"), "versoes_no_banco": dvs},
                {"nome": "Conjunto rotulado manualmente (MANUALLY_LABELED)", "data_origin": "MANUALLY_LABELED", "selo": "AUSENTE", "versao": None}]
    eng = STATE.engine
    engine = {"engine_version": SETTINGS.engine_version, "weights": eng.weights() if eng else None, "proposal_ttl_minutes": SETTINGS.proposal_ttl_minutes,
              "explicacao": "FINAL_SCORE = w_ML·ML_SCORE + w_REGRAS·BUSINESS_RULE_SCORE + w_DIST·DISTANCE_SCORE; os pesos são premissas do projeto, não calibradas com dados reais."}
    return AiOut(ranker=r, parser=ai_info.parser_block(), engine=engine, lote_misto=mixed, limitacoes=ai_info.limitations(mixed), glossario=ai_info.GLOSSARIO, datasets=datasets, rotulo=ai_info.ROTULO)


# ------------------------------------------------------------------------------------------------ 10. Segurança e sistema
@router.get("/security", response_model=SecurityOut, summary="ADMIN: relatórios SAST (Bandit/Trivy/pip-audit/gitleaks) e saúde da aplicação")
def security(db: Session = Depends(get_db), user: m.User = Depends(audit_dep("security"))):
    ok, why = STATE.ready()
    desde = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    aud = [{"outcome": o, "n": int(n)} for o, n in db.execute(select(m.AuditLog.outcome, func.count()).where(m.AuditLog.at >= desde).group_by(m.AuditLog.outcome).order_by(m.AuditLog.outcome))]
    top = [{"acao": a, "n": int(n)} for a, n in db.execute(select(m.AuditLog.action, func.count()).where(m.AuditLog.at >= desde).group_by(m.AuditLog.action).order_by(func.count().desc()).limit(8))]
    users = [{"perfil": p, "ativos": int(n)} for p, n in db.execute(select(m.User.role, func.count()).where(m.User.is_active).group_by(m.User.role).order_by(m.User.role))]
    sistema = {"pronto": ok, "motivo": why, "ambiente": "production" if IS_PRODUCTION else "development", "model_version": STATE.ranker.meta["model_version"] if STATE.ranker else None,
               "parser_version": STATE.parser.version if STATE.parser else None, "engine_version": SETTINGS.engine_version, "orgs_ranqueaveis": len(STATE.index.orgs) if STATE.index else None,
               "auditoria_24h_por_resultado": aud, "auditoria_24h_principais_acoes": top, "usuarios_ativos_por_perfil": users,
               "limitacoes": ["token estático por usuário; rate limit e rotação automática de tokens ficam para a Fase 4 (ver security/STRIDE.md)", "TLS é fornecido pela plataforma de hospedagem quando publicado"]}
    return SecurityOut(relatorios=security_reports.compute(), sistema=sistema)


# ------------------------------------------------------------------------------------------------ 11. Logística: estratégias (simulação)
@router.post("/logistics/strategies", status_code=200, summary="ADMIN: compara estratégias de logística (ONG mais próxima × ranking híbrido × ranking híbrido com rota) — SIMULAÇÃO reprodutível")
def logistics_strategies(body: StrategiesIn, db: Session = Depends(get_db), user: m.User = Depends(audit_dep("logistics_strategies"))):
    from routing import strategies
    if STATE.engine is None:
        raise HTTPException(503, "motor de match indisponível")
    try:
        return strategies.compare_strategies(db, STATE.engine, n_lots=body.n_lots, seed=body.seed, radius_km=body.raio_km, time_limit_s=body.tempo_solver_s)
    except strategies.StrategyError as e:
        raise HTTPException(422, str(e)) from e
