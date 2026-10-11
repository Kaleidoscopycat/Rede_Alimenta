"""Tempo médio de match a partir dos timestamps de match_events, SEPARADO por data_origin (simulado × uso real)."""
from __future__ import annotations

from collections import defaultdict
from statistics import mean, median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import models as m


def match_time_metrics(session: Session) -> dict[str, Any]:
    evs = session.execute(select(m.MatchEvent.match_id, m.MatchEvent.event_type, m.MatchEvent.at, m.MatchEvent.data_origin, m.MatchEvent.organization_id).order_by(m.MatchEvent.id)).all()
    reg = {d.id: d.created_at for d in session.scalars(select(m.Donation).join(m.Match, m.Match.donation_id == m.Donation.id).where(m.Donation.entry_channel == "API"))}
    mt = {x.id: (x.donation_id, x.data_origin) for x in session.scalars(select(m.Match))}
    by_match: dict[Any, list] = defaultdict(list)
    for e in evs:
        by_match[e.match_id].append(e)
    acc: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    n_matches: dict[str, int] = defaultdict(int)
    for mid, es in by_match.items():
        did, origin = mt[mid]
        n_matches[origin] += 1
        first_prop = next((e for e in es if e.event_type == "PROPOSED"), None)
        if first_prop and did in reg:
            acc[origin]["doacao_registrada_ate_primeira_proposta_s"].append((first_prop.at - reg[did]).total_seconds())
        last_prop = None
        for e in es:
            if e.event_type == "PROPOSED":
                last_prop = e
            elif e.event_type in ("ACCEPTED", "DECLINED") and last_prop is not None:
                acc[origin]["proposta_ate_resposta_s"].append((e.at - last_prop.at).total_seconds())
            if e.event_type == "ACCEPTED" and did in reg:
                acc[origin]["doacao_registrada_ate_aceite_s"].append((e.at - reg[did]).total_seconds())
            if e.event_type == "COLLECTED":
                acc_e = next((x for x in es if x.event_type == "ACCEPTED"), None)
                if acc_e:
                    acc[origin]["aceite_ate_coleta_s"].append((e.at - acc_e.at).total_seconds())
    out: dict[str, Any] = {}
    for origin, d in acc.items():
        out[origin] = {"n_matches": n_matches[origin], **{k: {"n": len(v), "media_s": round(mean(v), 3), "mediana_s": round(median(v), 3)} for k, v in d.items()}}
    for origin in n_matches:
        out.setdefault(origin, {"n_matches": n_matches[origin]})
    out["_nota"] = ("Tempos vindos de data_origin=SIMULATED são de EXECUÇÕES DE DEMONSTRAÇÃO sobre doações simuladas (respostas dadas por contas de teste); "
                    "NÃO representam o tempo real de ONGs. Apenas USER_ENTERED reflete uso real (hoje: nenhum).")
    return out
