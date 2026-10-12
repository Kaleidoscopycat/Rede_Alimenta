"""Schemas da API v1 (Fase 2 Parte 1). Entrada estrita (extra=forbid). Nenhuma pessoa física é aceita ou retornada."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.schemas import Categoria

Perecibilidade = Literal["NAO_PERECIVEL", "PERECIVEL_BAIXO_RISCO", "PERECIVEL_REFRIGERADO_CONGELADO", "PRONTO_ALTO_RISCO"]
Role = Literal["DONOR", "ORG", "ADMIN"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- identidade
class MeOut(BaseModel):
    user_id: uuid.UUID
    role: Role
    label: str
    donor_id: Optional[uuid.UUID] = None
    organization_id: Optional[uuid.UUID] = None
    is_demo: bool
    data_origin_scope: str = Field(description="SIMULATED para conta de demonstração (opera só sobre dados simulados); USER_ENTERED para conta real; ADMIN: todas")
    auth_limitations: str


class UserCreate(Strict):
    role: Role
    label: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9 ._\-]+$", description="Rótulo da conta (NÃO use nome de pessoa física)")
    donor_id: Optional[uuid.UUID] = None
    organization_id: Optional[uuid.UUID] = None
    is_demo: bool = False


class UserCreated(BaseModel):
    user_id: uuid.UUID
    role: Role
    label: str
    token: str = Field(description="Exibido UMA única vez; só o hash é armazenado")
    aviso: str


# ---------------------------------------------------------------- organizações
class LocationOut(BaseModel):
    lat: Optional[float]
    lon: Optional[float]
    location_precision: str
    geo_quality: Optional[str]
    rankable_by_distance: bool
    coord_source: str
    aviso: Optional[str] = None


class ProfileOut(BaseModel):
    data_origin: str
    capacity_max_kg_day: float
    cold_chamber: bool
    open_hour: float
    close_hour: float
    open_days_mask: int
    accepted_categories: list[str]
    has_fleet: bool
    fleet_refrigerated: bool
    aviso: Optional[str] = None


class OrganizationPublicView(BaseModel):
    """Visão de DONOR (e de ORG para outra organização): só identificação pública mínima; sem perfil declarado, coordenadas, origem do registro ou capacidade."""
    perfil: Literal["PUBLICA"] = "PUBLICA"
    ong_id: str
    ong_tipo: str
    uf: Optional[str]
    municipio_ibge: Optional[int]
    platform_status: str
    aviso: str


class OrganizationOut(BaseModel):
    perfil: Literal["COMPLETA"] = "COMPLETA"
    id: uuid.UUID
    ong_id: str
    ong_tipo: str
    uf: Optional[str]
    municipio_ibge: Optional[int]
    source: str
    source_record_id: str
    source_url: str
    last_verified_at: dt.datetime
    data_origin: str
    platform_status: str
    license_review_status: str
    location: LocationOut
    profile: Optional[ProfileOut] = None
    aviso: str


class ProfileIn(Strict):
    capacity_max_kg_day: float = Field(gt=0, le=1_000_000)
    capacity_min_kg_day: Optional[float] = Field(None, ge=0)
    cold_chamber: bool
    open_hour: float = Field(ge=0, le=24)
    close_hour: float = Field(ge=0, le=24)
    open_days: list[int] = Field(min_length=1, description="0=segunda ... 6=domingo")
    accepted_categories: list[Categoria] = Field(min_length=1)
    has_fleet: bool = False
    fleet_capacity_kg: Optional[float] = Field(None, gt=0)
    fleet_refrigerated: bool = False

    @model_validator(mode="after")
    def _chk(self):
        if self.close_hour <= self.open_hour:
            raise ValueError("horário de fechamento deve ser maior que o de abertura")
        if any(d < 0 or d > 6 for d in self.open_days):
            raise ValueError("open_days deve conter inteiros de 0 a 6")
        return self


# ---------------------------------------------------------------- doadores
class DonorCreate(Strict):
    donor_type: str = Field(min_length=2, max_length=40, pattern=r"^[A-Z_]+$")
    donor_size: Optional[Literal["PEQUENO", "MEDIO", "GRANDE"]] = None
    display_name: Optional[str] = Field(None, max_length=160, description="Nome da PESSOA JURÍDICA (opcional). Não informe pessoa física.")
    municipio_ibge: int = Field(ge=1_100_000, le=5_300_000)
    lat: Optional[float] = Field(None, ge=-34.0, le=6.0)
    lon: Optional[float] = Field(None, ge=-75.0, le=-28.0)
    pickup_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    pickup_start_h: float = Field(8.0, ge=0, le=24)
    pickup_end_h: float = Field(17.0, ge=0, le=24)
    load_minutes: int = Field(30, ge=0, le=600)

    @model_validator(mode="after")
    def _chk(self):
        if (self.lat is None) != (self.lon is None):
            raise ValueError("informe lat e lon juntos")
        if self.pickup_end_h <= self.pickup_start_h:
            raise ValueError("janela de retirada inválida")
        if not self.pickup_days or any(d < 0 or d > 6 for d in self.pickup_days):
            raise ValueError("pickup_days deve conter inteiros de 0 a 6")
        return self


class DonorOut(BaseModel):
    id: uuid.UUID
    donor_type: str
    donor_size: Optional[str]
    display_name: Optional[str]
    municipio_ibge: int
    data_origin: str
    location_precision: Optional[str]
    pickup_days_mask: int
    pickup_start_h: float
    pickup_end_h: float


# ---------------------------------------------------------------- doações / parser
class ParseIn(Strict):
    texto: str = Field(min_length=3, max_length=500)
    donor_id: Optional[uuid.UUID] = Field(None, description="Somente ADMIN: doador a que o texto se refere (define a origem dos dados)")


class FieldOut(BaseModel):
    value: Any = None
    confidence: Optional[float] = None
    status: str
    note: Optional[str] = None


class ParseOut(BaseModel):
    fields: dict[str, FieldOut]
    validity_source: str
    validity_flags: list[str]
    alerts: list[str]
    blocked: dict[str, bool]
    needs_human_confirmation: list[str]
    quantidade_texto: dict[str, Any]
    parser_version: str
    confidence_threshold: float
    threshold_note: str
    training_data_origin: str
    manually_labeled_evaluation: str
    aviso: str


class DonationIn(Strict):
    donor_id: Optional[uuid.UUID] = Field(None, description="Somente ADMIN")
    texto: Optional[str] = Field(None, min_length=3, max_length=500)
    categoria: Optional[Categoria] = None
    exige_refrigeracao: Optional[bool] = None
    dias_ate_validade: Optional[int] = Field(None, ge=-3650, le=3650)
    validade_data: Optional[dt.date] = None
    quantidade_kg: Optional[float] = Field(None, gt=0, le=100_000)
    contem_alergenico: bool = False
    janela_retirada_inicio_h: Optional[float] = Field(None, ge=0, le=24)
    janela_retirada_fim_h: Optional[float] = Field(None, ge=0, le=24)
    tempo_carga_min: Optional[int] = Field(None, ge=0, le=600)
    dias_retirada: Optional[list[int]] = None

    @model_validator(mode="after")
    def _chk(self):
        if not self.texto and not self.categoria:
            raise ValueError("informe `texto` e/ou campos estruturados (ao menos `categoria`)")
        if self.dias_ate_validade is not None and self.validade_data is not None:
            raise ValueError("informe `dias_ate_validade` OU `validade_data`")
        if self.dias_retirada is not None and (not self.dias_retirada or any(d < 0 or d > 6 for d in self.dias_retirada)):
            raise ValueError("dias_retirada deve conter inteiros de 0 a 6")
        return self


class ConfirmIn(Strict):
    categoria: Optional[Categoria] = None
    perecibilidade: Optional[Perecibilidade] = None
    exige_refrigeracao: Optional[bool] = None
    dias_ate_validade: Optional[int] = Field(None, ge=-3650, le=3650)
    validade_data: Optional[dt.date] = None
    quantidade_kg: Optional[float] = Field(None, gt=0, le=100_000)
    contem_alergenico: Optional[bool] = None
    accept_fields: list[Literal["categoria", "perecibilidade", "exige_refrigeracao", "dias_ate_validade", "quantidade_kg"]] = Field(
        default_factory=list, description="Campos extraídos que o doador aceita como estão (confirmação explícita)")

    @model_validator(mode="after")
    def _chk(self):
        if self.dias_ate_validade is not None and self.validade_data is not None:
            raise ValueError("informe `dias_ate_validade` OU `validade_data`")
        return self


class DonationOut(BaseModel):
    id: uuid.UUID
    donor_id: uuid.UUID
    data_origin: str
    status: str
    block_reason: Optional[str]
    pending_fields: list[str]
    raw_text: Optional[str]
    categoria: Optional[str]
    perecibilidade: Optional[str]
    exige_refrigeracao: Optional[bool]
    quantity_kg: Optional[float]
    validity_days: Optional[int]
    expires_at: Optional[dt.datetime]
    validity_source: Optional[str]
    refeicoes_equivalentes: Optional[float] = Field(None, description="kg ÷ 0,4 (premissa da equipe, configurável); em dados SIMULADOS é simulação")
    premissa_kg_por_refeicao: float = 0.4
    fields: dict[str, Any]
    parser_version: Optional[str]
    created_at: dt.datetime
    confirmed_at: Optional[dt.datetime]
    aviso: str


# ---------------------------------------------------------------- matches
class MatchIn(Strict):
    donation_id: uuid.UUID
    top_n: int = Field(5, ge=1, le=15, description="Quantas candidatas devolver na resposta (o ranking completo fica armazenado)")


class RespondIn(Strict):
    accept: bool
    note: Optional[str] = Field(None, max_length=300)


class OutcomeIn(Strict):
    result: Literal["COLLECTED", "FAILED"]
    note: Optional[str] = Field(None, max_length=300)


class BatchIn(Strict):
    donation_ids: list[uuid.UUID] = Field(min_length=2, max_length=500)
    at: Optional[dt.datetime] = Field(None, description="Relógio da rodada (SIMULADO, para lotes históricos). Padrão: agora")


class PredictionIn(Strict):
    """Predição direta (sem criar doação/match): mesmo contrato de LoteIn da Fase 1 + donor_id (ADMIN)."""
    donor_id: Optional[uuid.UUID] = None
    categoria: Optional[Categoria] = None
    descricao_texto: Optional[str] = Field(None, max_length=500)
    quantidade_kg: float = Field(..., gt=0, le=100_000)
    horas_ate_validade: Optional[float] = Field(None, gt=0, le=24 * 365)
    exige_refrigeracao: bool = False
    contem_alergenico: bool = False
    janela_retirada_inicio_h: float = Field(8.0, ge=0, le=24)
    janela_retirada_fim_h: float = Field(17.0, ge=0, le=24)
    tempo_carga_min: float = Field(30.0, ge=0, le=600)
    dias_retirada: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    municipio_ibge: Optional[int] = Field(None, ge=1_100_000, le=5_300_000)
    lat: Optional[float] = Field(None, ge=-34.0, le=6.0)
    lon: Optional[float] = Field(None, ge=-75.0, le=-28.0)
    top_n: int = Field(5, ge=1, le=15)
