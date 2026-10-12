"""Visões por perfil (Fase 3 Parte 1, seção 3). Cada perfil tem o PRÓPRIO schema de resposta (response_model), que também descarta qualquer chave extra:
  DONOR → só o que o doador precisa (sua doação, itens, situação e a ONG que aceitou); NUNCA ranking, scores, elegibilidade, modelo ou latências.
  ORG   → a doação dirigida a ela, a análise textual SEM scores e a própria candidatura (sem as demais candidatas).
  ADMIN → tudo (inclusive ranking completo, scores, modelo e predictions); o acesso é auditado (`admin.access`).
A união é discriminada pelo campo `perfil`."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


# ------------------------------------------------------------------------------------------------------------------ itens
class ItemDonorView(BaseModel):
    id: int
    produto: Optional[str]
    description: Optional[str]
    categoria: Optional[str]
    perecibilidade: Optional[str]
    exige_refrigeracao: Optional[bool]
    quantity: Optional[float]
    unit: Optional[str]
    unit_weight: Optional[float]
    unit_weight_unit: Optional[str]
    quantity_kg: Optional[float]
    weight_estimated: bool = False
    weight_note: Optional[str] = None
    expires_at: Optional[dt.datetime]
    validity_days: Optional[int]
    validity_precision: Optional[str]
    validity_note: Optional[str] = None
    validity_source: Optional[str]
    entry_source: Optional[str]
    pending_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


class ItemOrgView(BaseModel):
    produto: Optional[str]
    description: Optional[str]
    categoria: Optional[str]
    perecibilidade: Optional[str]
    exige_refrigeracao: Optional[bool]
    quantity: Optional[float]
    unit: Optional[str]
    unit_weight: Optional[float]
    unit_weight_unit: Optional[str]
    quantity_kg: Optional[float]
    weight_estimated: bool = False
    weight_note: Optional[str] = None
    expires_at: Optional[dt.datetime]
    validity_precision: Optional[str]
    validity_note: Optional[str] = None


class ItemAdminView(ItemDonorView):
    data_origin: str
    weight_basis: Optional[str]
    parser_suggestion: Optional[dict[str, Any]]
    created_at: Optional[dt.datetime]
    updated_at: Optional[dt.datetime]


# ------------------------------------------------------------------------------------------------------------------ doações
class Resumo(BaseModel):
    n_items: int
    quantity_kg: Optional[float]
    incomplete_weight: bool
    categories: list[str]
    is_mixed_batch: bool
    expires_at: Optional[dt.datetime]
    validity_days: Optional[int]
    exige_refrigeracao: Optional[bool]
    perecibilidade: Optional[str]
    refeicoes_equivalentes: Optional[float] = Field(None, description="kg ÷ 0,4 (premissa da equipe, configurável); em dados SIMULADOS é simulação")
    premissa_kg_por_refeicao: float = 0.4


class Header(BaseModel):
    """Campos do cabeçalho da doação (AGREGADOS dos itens; mantidos no nível superior por compatibilidade com o contrato da Fase 2)."""
    donor_id: uuid.UUID
    categoria: Optional[str] = None
    perecibilidade: Optional[str] = None
    exige_refrigeracao: Optional[bool] = None
    quantity_kg: Optional[float] = None
    validity_days: Optional[int] = None
    expires_at: Optional[dt.datetime] = None
    validity_source: Optional[str] = None
    refeicoes_equivalentes: Optional[float] = None
    premissa_kg_por_refeicao: float = 0.4


class DonorDonationView(Header):
    perfil: Literal["DONOR"] = "DONOR"
    id: uuid.UUID
    data_origin: str
    status: str
    situacao: str
    block_reason: Optional[str]
    pending_fields: list[str]
    raw_text: Optional[str]
    items: list[ItemDonorView]
    resumo: Resumo
    alertas: list[str]
    contem_alergenico: bool
    janela_retirada: dict[str, Any]
    fields: dict[str, Any] = Field(default_factory=dict, description="Fluxo de texto único (anterior): campos extraídos e decisões, para conferência do doador")
    match_id: Optional[uuid.UUID] = None
    ong_aceita: Optional[str] = Field(None, description="Pseudônimo da ONG, só após o aceite")
    created_at: dt.datetime
    confirmed_at: Optional[dt.datetime]
    aviso: str


class OrgDonationView(BaseModel):
    perfil: Literal["ORG"] = "ORG"
    donation_id: uuid.UUID
    data_origin: str
    items: list[ItemOrgView]
    resumo: Resumo
    contem_alergenico: bool
    janela_retirada: dict[str, Any]
    doador: dict[str, Any]
    analise: list[str] = Field(description="Análise textual da IA sobre o lote (SEM scores): validade, refrigeração, lote misto, estimativas")
    aviso: str


class AdminDonationView(Header):
    perfil: Literal["ADMIN"] = "ADMIN"
    id: uuid.UUID
    data_origin: str
    status: str
    block_reason: Optional[str]
    entry_channel: str
    raw_text: Optional[str]
    items: list[ItemAdminView]
    resumo: Resumo
    alertas: list[str]
    contem_alergenico: bool
    janela_retirada: dict[str, Any]
    fields: dict[str, Any]
    parser_version: Optional[str]
    created_by: Optional[uuid.UUID]
    created_at: dt.datetime
    confirmed_at: Optional[dt.datetime]
    aggregated_at: Optional[dt.datetime]
    aviso: str


DonationView = Annotated[Union[DonorDonationView, AdminDonationView], Field(discriminator="perfil")]


# ------------------------------------------------------------------------------------------------------------------ matches
class DonorMatchView(BaseModel):
    perfil: Literal["DONOR"] = "DONOR"
    id: uuid.UUID
    donation_id: uuid.UUID
    data_origin: str
    status: str
    situacao: str
    ong_aceita: Optional[str] = None
    created_at: dt.datetime
    updated_at: dt.datetime
    closed_at: Optional[dt.datetime]
    aviso: str


class OrgCandidacy(BaseModel):
    dist_km: Optional[float]
    distancia_aproximada: bool
    tempo_deslocamento_est_h: Optional[float]
    espera_janela_h: Optional[float]
    folga_validade_h: Optional[float]
    capacidade_restante_kg: Optional[float]
    explicacao: list[str]


class OrgMatchView(BaseModel):
    perfil: Literal["ORG"] = "ORG"
    id: uuid.UUID
    data_origin: str
    status: str
    awaiting_my_response: bool
    proposal_expires_at: Optional[dt.datetime]
    my_candidacy: Optional[OrgCandidacy]
    donation: OrgDonationView
    created_at: dt.datetime
    closed_at: Optional[dt.datetime]
    aviso: str


class AdminMatchView(BaseModel):
    """ADMIN: contrato completo (ranking, scores, elegibilidade, pesos, latências)."""
    model_config = ConfigDict(extra="allow")
    perfil: Literal["ADMIN"] = "ADMIN"
    id: str
    donation_id: str
    status: str


MatchView = Annotated[Union[DonorMatchView, OrgMatchView, AdminMatchView], Field(discriminator="perfil")]
