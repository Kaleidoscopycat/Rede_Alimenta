"""Construtores das visões por perfil (ver api/schemas_views.py). Toda saída para DONOR/ORG passa por aqui: nada de ranking, score, modelo ou elegibilidade."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from api import donation_rules as drules
from api import item_rules as rules
from api.aggregation import MIXED_BATCH_LIMITATION, SPREAD_ADVICE, aggregate
from api.items import is_item_managed, item_missing, item_weight_info
from api.schemas_views import (AdminDonationView, AdminMatchView, DonorDonationView, DonorMatchView, ItemAdminView, ItemDonorView, ItemOrgView, OrgCandidacy, OrgDonationView,
                               OrgMatchView, Resumo)
from api.state import STATE
from core.settings import DONATION
from database import models as m

AVISO_DOACAO = ("A plataforma não afirma que o alimento é próprio para consumo; o doador é responsável pela informação. "
                "Doações SIMULATED vêm de doador simulado (conta de demonstração) e não representam uso real.")
AVISO_ORG = ("Análise de apoio: não afirma que o alimento é próprio para consumo; confirme as condições na coleta. Capacidade, horários e refrigeração das ONGs em dados SIMULATED "
             "são declarados simulados. Distâncias são em linha reta (aproximadas quando há centroide de município).")
SITUACAO_DOACAO = {"DRAFT": "Rascunho: adicione e confirme os itens", "PENDING_CONFIRMATION": "Aguardando a sua confirmação de campos pendentes", "READY": "Pronta: pode buscar uma ONG",
                   "BLOCKED_EXPIRED": "Bloqueada: há item com validade vencida", "BLOCKED_NO_VALIDITY": "Bloqueada: há item sem validade",
                   "MATCHING": "Buscando ONG: aguardando resposta", "MATCHED": "Uma ONG aceitou a doação", "NO_MATCH": "Nenhuma ONG disponível no momento", "HISTORICAL": "Registro histórico simulado"}
SITUACAO_MATCH = {"PROPOSED": "Aguardando resposta de uma ONG", "ACCEPTED": "Uma ONG aceitou a doação", "COLLECTED": "Coleta concluída", "FAILED": "Coleta não concluída",
                  "EXHAUSTED": "Nenhuma ONG disponível no momento", "DECLINED": "Recusada; buscando outra ONG", "EXPIRED": "Sem resposta; buscando outra ONG"}
AVISO_MATCH_ADMIN = ("Ranking de apoio: ML_SCORE vem de modelo treinado em dados SIMULADOS; capacidade/horários/refrigeração das ONGs são DECLARADOS SIMULADOS; distâncias são em linha reta "
                     "(haversine), aproximadas quando há centroide de município; pesos do FINAL_SCORE são premissas. Requer confirmação humana; a plataforma não atesta a segurança do alimento.")
DONOR_MATCH_NOTE = "Você acompanha só a situação da doação: a plataforma não mostra ao doador o ranqueamento nem as pontuações das ONGs."


def _items(db: Session, d: m.Donation) -> list[m.DonationItem]:
    return list(db.scalars(select(m.DonationItem).where(m.DonationItem.donation_id == d.id).order_by(m.DonationItem.id)))


def item_donor(it: m.DonationItem) -> ItemDonorView:
    est, note = item_weight_info(it, STATE.unit_mass)
    return ItemDonorView(id=it.id, produto=it.produto, description=it.description, categoria=it.categoria, perecibilidade=it.perecibilidade, exige_refrigeracao=it.exige_refrigeracao,
                         quantity=it.quantity, unit=it.unit, unit_weight=it.unit_weight, unit_weight_unit=it.unit_weight_unit, quantity_kg=it.quantity_kg, weight_estimated=est,
                         weight_note=note, expires_at=it.expires_at, validity_days=it.validity_days, validity_precision=it.validity_precision,
                         validity_note=rules.validity_note(it.validity_precision, it.expires_at), validity_source=it.validity_source, entry_source=it.entry_source,
                         pending_fields=list(it.pending_fields or []), missing_fields=item_missing(it) if it.entry_source else [])


def item_org(it: m.DonationItem) -> ItemOrgView:
    est, note = item_weight_info(it, STATE.unit_mass)
    return ItemOrgView(produto=it.produto, description=it.description, categoria=it.categoria, perecibilidade=it.perecibilidade, exige_refrigeracao=it.exige_refrigeracao,
                       quantity=it.quantity, unit=it.unit, unit_weight=it.unit_weight, unit_weight_unit=it.unit_weight_unit, quantity_kg=it.quantity_kg, weight_estimated=est, weight_note=note,
                       expires_at=it.expires_at, validity_precision=it.validity_precision, validity_note=rules.validity_note(it.validity_precision, it.expires_at))


def item_admin(it: m.DonationItem) -> ItemAdminView:
    return ItemAdminView(**item_donor(it).model_dump(), data_origin=it.data_origin, weight_basis=it.weight_basis, parser_suggestion=it.parser_suggestion, created_at=it.created_at,
                         updated_at=it.updated_at)


def resumo(d: m.Donation, items: list[m.DonationItem]) -> Resumo:
    incomplete = any(i.quantity_kg is None for i in items)
    cats = list(d.categories or ([d.categoria] if d.categoria else []))
    return Resumo(n_items=len(items), quantity_kg=d.quantity_kg, incomplete_weight=incomplete, categories=cats, is_mixed_batch=bool(d.is_mixed_batch), expires_at=d.expires_at,
                  validity_days=d.validity_days, exige_refrigeracao=d.exige_refrigeracao, perecibilidade=d.perecibilidade,
                  refeicoes_equivalentes=round(d.quantity_kg / 0.4, 1) if d.quantity_kg else None)


def alerts(d: m.Donation, items: list[m.DonationItem], now=None) -> list[str]:
    out: list[str] = []
    if not items:
        return out
    from api.aggregation import ItemAgg as IA
    import datetime as dt
    agg = aggregate([IA(i.id, i.categoria, i.produto, i.quantity_kg, i.expires_at, i.exige_refrigeracao, i.perecibilidade) for i in items], now or dt.datetime.now(dt.timezone.utc))
    if agg.spread_warning:
        nomes = ", ".join(i.produto or "item" for i in items if i.id in agg.short_validity_item_ids)
        out.append(f"Itens com validades muito diferentes (até {agg.spread_days} dias de diferença; limite de aviso {DONATION.validity_spread_warn_days}). {SPREAD_ADVICE} Mais próximos: {nomes}.")
    if d.is_mixed_batch:
        out.append("Lote misto (várias categorias): a ONG precisa aceitar todas as categorias. " + MIXED_BATCH_LIMITATION)
    if any(it.weight_basis in ("VOLUME_CONVERTIDO", "MASSA_UNITARIA_CATEGORIA") for it in items):
        out.append("Há peso ESTIMADO (volume convertido em kg por premissa sem fonte): confira o peso real.")
    if any(it.validity_precision == "MONTH" for it in items):
        out.append("Itens com validade só em mês/ano: usamos o último dia do mês (a validade real pode ser anterior; confirme a data exata se possível).")
    return out


def _pending_donation(d: m.Donation, items: list[m.DonationItem]) -> list[str]:
    if is_item_managed(d):
        return [f"{i.produto or 'item'}: {', '.join(item_missing(i))}" for i in items if item_missing(i)]
    return [k for k, f in (d.fields or {}).items() if isinstance(f, dict) and k in drules.REQUIRED and (f.get("status") in drules.PENDING_STATES or f.get("final") is None)]


def _header(d: m.Donation) -> dict[str, Any]:
    return dict(donor_id=d.donor_id, categoria=d.categoria, perecibilidade=d.perecibilidade, exige_refrigeracao=d.exige_refrigeracao, quantity_kg=d.quantity_kg,
                validity_days=d.validity_days, expires_at=d.expires_at, validity_source=d.validity_source, refeicoes_equivalentes=round(d.quantity_kg / 0.4, 1) if d.quantity_kg else None)


def _window(d: m.Donation) -> dict[str, Any]:
    return {"inicio_h": d.pickup_start_h, "fim_h": d.pickup_end_h, "dias_mask": d.pickup_days_mask, "tempo_carga_min": d.load_minutes}


def last_match(db: Session, d: m.Donation) -> m.Match | None:
    return db.scalars(select(m.Match).where(m.Match.donation_id == d.id).order_by(m.Match.created_at.desc())).first()


def donation_donor(db: Session, d: m.Donation, now=None) -> DonorDonationView:
    items = _items(db, d)
    mt = last_match(db, d) if d.status in ("MATCHING", "MATCHED", "NO_MATCH", "READY") else None
    ong = None
    if mt is not None and mt.status in ("ACCEPTED", "COLLECTED") and mt.current_org_id:
        o = db.get(m.Organization, mt.current_org_id)
        ong = o.ong_id if o else None
    situacao = SITUACAO_MATCH.get(mt.status) if (mt is not None and d.status in ("MATCHING", "MATCHED", "NO_MATCH")) else SITUACAO_DOACAO.get(d.status, d.status)
    return DonorDonationView(**_header(d), id=d.id, data_origin=d.data_origin, status=d.status, situacao=situacao or d.status, block_reason=d.block_reason, pending_fields=_pending_donation(d, items),
                             raw_text=d.raw_text, items=[item_donor(i) for i in items], resumo=resumo(d, items), alertas=alerts(d, items, now), contem_alergenico=d.contem_alergenico,
                             janela_retirada=_window(d), fields=d.fields or {}, match_id=mt.id if mt is not None else None, ong_aceita=ong, created_at=d.created_at,
                             confirmed_at=d.confirmed_at, aviso=AVISO_DOACAO)


def donation_admin(db: Session, d: m.Donation, now=None) -> AdminDonationView:
    items = _items(db, d)
    return AdminDonationView(**_header(d), id=d.id, data_origin=d.data_origin, status=d.status, block_reason=d.block_reason, entry_channel=d.entry_channel, raw_text=d.raw_text,
                             items=[item_admin(i) for i in items], resumo=resumo(d, items), alertas=alerts(d, items, now), contem_alergenico=d.contem_alergenico,
                             janela_retirada=_window(d), fields=d.fields or {}, parser_version=d.parser_version, created_by=d.created_by,
                             created_at=d.created_at, confirmed_at=d.confirmed_at, aggregated_at=d.aggregated_at, aviso=AVISO_DOACAO)


def donation_view(db: Session, d: m.Donation, user: m.User, now=None):
    return donation_admin(db, d, now) if user.role == "ADMIN" else donation_donor(db, d, now)


def analysis_for_org(d: m.Donation, items: list[m.DonationItem]) -> list[str]:
    """Texto da IA para a ONG — SEM scores. Só fatos do lote e avisos."""
    out = [f"Lote com {len(items)} item(ns)" + (f", {d.quantity_kg:g} kg no total" if d.quantity_kg else "") + (f", {len(d.categories or [])} categoria(s)." if d.categories else ".")]
    if d.expires_at is not None:
        out.append(f"Validade mais próxima do lote: {d.expires_at.strftime('%d/%m/%Y')} (todo o lote deve ser retirado antes dela).")
    out.append("Exige refrigeração: " + ("sim" if d.exige_refrigeracao else "não" if d.exige_refrigeracao is False else "não informado") + ".")
    out.extend(alerts(d, items))
    if d.contem_alergenico:
        out.append("O doador informou que o lote pode conter alergênicos.")
    return out


def donation_org(db: Session, d: m.Donation) -> OrgDonationView:
    items = _items(db, d)
    donor = db.get(m.Donor, d.donor_id)
    return OrgDonationView(donation_id=d.id, data_origin=d.data_origin, items=[item_org(i) for i in items], resumo=resumo(d, items), contem_alergenico=d.contem_alergenico,
                           janela_retirada=_window(d), doador={"tipo": donor.donor_type if donor else None, "porte": donor.donor_size if donor else None,
                                                                "municipio_ibge": donor.municipio_ibge if donor else None},
                           analise=analysis_for_org(d, items), aviso=AVISO_ORG)


SAFE_EXPL = ("Distância", "Espera", "Capacidade, horários")  # linhas da explicação que NÃO trazem scores


def candidacy_for_org(row: dict[str, Any] | None) -> OrgCandidacy | None:
    if row is None:
        return None
    expl = [e for e in row.get("explicacao", []) if e.startswith(SAFE_EXPL)]
    return OrgCandidacy(dist_km=row.get("dist_km"), distancia_aproximada=bool(row.get("distancia_aproximada")), tempo_deslocamento_est_h=row.get("tempo_deslocamento_est_h"),
                        espera_janela_h=row.get("espera_janela_h"), folga_validade_h=row.get("folga_validade_h"), capacidade_restante_kg=row.get("capacidade_restante_kg"), explicacao=expl)


def match_donor(db: Session, mt: m.Match) -> DonorMatchView:
    ong = None
    if mt.status in ("ACCEPTED", "COLLECTED", "FAILED") and mt.current_org_id:
        o = db.get(m.Organization, mt.current_org_id)
        ong = o.ong_id if o else None
    return DonorMatchView(id=mt.id, donation_id=mt.donation_id, data_origin=mt.data_origin, status=mt.status, situacao=SITUACAO_MATCH.get(mt.status, mt.status), ong_aceita=ong,
                          created_at=mt.created_at, updated_at=mt.updated_at, closed_at=mt.closed_at, aviso=DONOR_MATCH_NOTE)


def match_org(db: Session, mt: m.Match, user: m.User) -> OrgMatchView:
    d = db.get(m.Donation, mt.donation_id)
    mine = next((r for r in mt.ranking if r["org_id"] == str(user.organization_id)), None)
    return OrgMatchView(id=mt.id, data_origin=mt.data_origin, status=mt.status, awaiting_my_response=mt.status == "PROPOSED" and mt.current_org_id == user.organization_id,
                        proposal_expires_at=mt.proposal_expires_at if mt.current_org_id == user.organization_id else None, my_candidacy=candidacy_for_org(mine),
                        donation=donation_org(db, d), created_at=mt.created_at, closed_at=mt.closed_at, aviso=AVISO_ORG)


def org_label(db: Session, org_id) -> str | None:
    if not org_id:
        return None
    o = db.get(m.Organization, org_id)
    return o.ong_id if o else None


def match_admin(db: Session, mt: m.Match, top_n: int | None = None) -> AdminMatchView:
    from match.engine import SCORE_LABELS
    d = db.get(m.Donation, mt.donation_id)
    ranking = mt.ranking if top_n is None else mt.ranking[:top_n]
    return AdminMatchView(id=str(mt.id), donation_id=str(mt.donation_id), status=mt.status, data_origin=mt.data_origin, engine_version=mt.engine_version, model_version=mt.model_version,
                          current_org=org_label(db, mt.current_org_id), current_position=mt.current_position, proposal_expires_at=mt.proposal_expires_at, latency_ms=mt.latency_ms,
                          created_at=mt.created_at, updated_at=mt.updated_at, closed_at=mt.closed_at, donation=donation_admin(db, d).model_dump(mode="json"),
                          score_definitions=SCORE_LABELS, aviso=AVISO_MATCH_ADMIN, ranking=ranking, n_candidates=len(mt.ranking), eligibility=mt.eligibility, weights=mt.weights)


def match_view(db: Session, mt: m.Match, user: m.User, top_n: int | None = None):
    if user.role == "ADMIN":
        return match_admin(db, mt, top_n)
    if user.role == "DONOR":
        return match_donor(db, mt)
    return match_org(db, mt, user)
