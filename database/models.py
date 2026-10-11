"""Modelos SQLAlchemy (PostgreSQL). Regras de origem dos dados garantidas também no banco (CHECK):

* `data_origin` ∈ PUBLIC | SIMULATED | USER_ENTERED (MANUALLY_LABELED não é gravado aqui: é conjunto de teste de ML).
* SIMULATED exige generator_version + dataset_version + seed; USER_ENTERED NÃO pode ter nenhum desses campos
  (um registro simulado nunca pode ser gravado como USER_ENTERED, nem o contrário).
Doadores e ONGs são pessoas jurídicas. `users` guarda só o mínimo para autenticação (rótulo de conta + hash do token).
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Optional

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text,
                        UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ORIGINS = ("PUBLIC", "SIMULATED", "USER_ENTERED")
ROLES = ("DONOR", "ORG", "ADMIN")


class Base(DeclarativeBase):
    pass


def _origin_checks(table: str, allowed: tuple[str, ...] = ORIGINS, trace: bool = True) -> list[CheckConstraint]:
    allowed_sql = ", ".join(f"'{a}'" for a in allowed)
    cks = [CheckConstraint(f"data_origin IN ({allowed_sql})", name=f"ck_{table}_origin")]
    if trace:
        cks += [
            CheckConstraint("data_origin <> 'SIMULATED' OR (generator_version IS NOT NULL AND dataset_version IS NOT NULL AND seed IS NOT NULL)", name=f"ck_{table}_sim_trace"),
            CheckConstraint("data_origin <> 'USER_ENTERED' OR (generator_version IS NULL AND dataset_version IS NULL AND seed IS NULL)", name=f"ck_{table}_user_notrace"),
        ]
    return cks


class SimTraceMixin:
    generator_version: Mapped[Optional[str]] = mapped_column(String(32))
    seed: Mapped[Optional[int]] = mapped_column(BigInteger)
    dataset_version: Mapped[Optional[str]] = mapped_column(String(80))


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ------------------------------------------------------------------ dados públicos (REAIS)
class PublicDataSource(Base):
    __tablename__ = "public_data_sources"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    organization: Mapped[Optional[str]] = mapped_column(String(200))
    dataset: Mapped[Optional[str]] = mapped_column(String(300))
    url: Mapped[Optional[str]] = mapped_column(Text)
    license_status: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(20))  # APPROVED | NEEDS_REVIEW | RESTRICTED
    commercial_use: Mapped[str] = mapped_column(String(60), default="NAO_CONFIRMADO")
    publication_cleared: Mapped[bool] = mapped_column(Boolean, default=False)  # liberada para publicação? (Fase 3 depende disto)
    raw_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    ingested_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[Optional[str]] = mapped_column(String(80))
    data_origin: Mapped[str] = mapped_column(String(12), default="PUBLIC")
    __table_args__ = (CheckConstraint("data_origin = 'PUBLIC'", name="ck_pds_origin"),
                      CheckConstraint("review_status IN ('APPROVED','NEEDS_REVIEW','RESTRICTED','REJECTED')", name="ck_pds_review"))


class PublicDatasetVersion(Base):
    __tablename__ = "public_dataset_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("public_data_sources.id"))
    version_label: Mapped[str] = mapped_column(String(120))
    raw_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    n_records: Mapped[int] = mapped_column(Integer)
    pipeline_version: Mapped[str] = mapped_column(String(40))
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    data_origin: Mapped[str] = mapped_column(String(12), default="PUBLIC")
    __table_args__ = (CheckConstraint("data_origin = 'PUBLIC'", name="ck_pdv_origin"), UniqueConstraint("source_id", "version_label", name="uq_pdv"))


class Municipality(Base):
    __tablename__ = "municipalities"
    ibge_code: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    uf: Mapped[str] = mapped_column(String(2))
    region: Mapped[Optional[str]] = mapped_column(String(2))
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)
    location_precision: Mapped[str] = mapped_column(String(24), default="MUNICIPALITY_CENTROID")
    coord_origin: Mapped[Optional[str]] = mapped_column(String(40))  # PROXY_TERCEIROS_MIT: origem primária NÃO confirmada
    source_id: Mapped[str] = mapped_column(ForeignKey("public_data_sources.id"))
    dataset_version_id: Mapped[Optional[int]] = mapped_column(ForeignKey("public_dataset_versions.id"))
    data_origin: Mapped[str] = mapped_column(String(12), default="PUBLIC")
    __table_args__ = (CheckConstraint("data_origin = 'PUBLIC'", name="ck_muni_origin"),)


class PublicIndicator(Base):
    __tablename__ = "public_indicators"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    municipio_ibge: Mapped[int] = mapped_column(ForeignKey("municipalities.ibge_code"), index=True)
    code: Mapped[str] = mapped_column(String(60))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[Optional[str]] = mapped_column(String(30))
    reference_period: Mapped[Optional[str]] = mapped_column(String(30))
    source_id: Mapped[str] = mapped_column(ForeignKey("public_data_sources.id"))
    dataset_version_id: Mapped[Optional[int]] = mapped_column(ForeignKey("public_dataset_versions.id"))
    data_origin: Mapped[str] = mapped_column(String(12), default="PUBLIC")
    __table_args__ = (CheckConstraint("data_origin = 'PUBLIC'", name="ck_pind_origin"), UniqueConstraint("municipio_ibge", "code", name="uq_pind"))


class FoodCategory(Base):
    __tablename__ = "food_categories"
    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    description: Mapped[str] = mapped_column(String(200))
    perecibilidade: Mapped[str] = mapped_column(String(40))
    typical_shelf_days_min: Mapped[Optional[float]] = mapped_column(Float)
    typical_shelf_days_max: Mapped[Optional[float]] = mapped_column(Float)
    unit_mass_kg: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    source: Mapped[str] = mapped_column(String(200))  # taxonomy_v0.2 (PREMISSA DO PROJETO; vida útil sem fonte)


# ------------------------------------------------------------------ organizações (ONGs REAIS)
class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    ong_id: Mapped[str] = mapped_column(String(24), unique=True)  # pseudônimo da Fase 1 (sem CNPJ/nome)
    ong_tipo: Mapped[str] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(ForeignKey("public_data_sources.id"))
    source_record_id: Mapped[str] = mapped_column(String(60))
    source_url: Mapped[str] = mapped_column(Text)
    last_verified_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    municipio_ibge: Mapped[Optional[int]] = mapped_column(ForeignKey("municipalities.ibge_code"), index=True)
    uf: Mapped[Optional[str]] = mapped_column(String(2), index=True)
    natureza_juridica: Mapped[Optional[float]] = mapped_column(Float)
    ano_fundacao: Mapped[Optional[int]] = mapped_column(SmallInteger)
    modalidade_rbba: Mapped[Optional[str]] = mapped_column(String(60))
    area_assistencia_social: Mapped[Optional[bool]] = mapped_column(Boolean)
    pipeline_version: Mapped[str] = mapped_column(String(20))
    license_review_status: Mapped[str] = mapped_column(String(20), default="NEEDS_REVIEW")
    # Entidade pública NÃO é cliente da plataforma até cadastro/aceite (platform_status = REGISTERED).
    platform_status: Mapped[str] = mapped_column(String(16), default="PUBLIC_RECORD")
    registered_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    data_origin: Mapped[str] = mapped_column(String(12), default="PUBLIC")
    location: Mapped["OrganizationLocation"] = relationship(back_populates="organization", uselist=False)
    profile: Mapped[Optional["OrganizationProfile"]] = relationship(back_populates="organization", uselist=False)
    __table_args__ = (CheckConstraint("data_origin = 'PUBLIC'", name="ck_org_origin"),
                      CheckConstraint("platform_status IN ('PUBLIC_RECORD','REGISTERED')", name="ck_org_status"),
                      UniqueConstraint("source", "source_record_id", name="uq_org_source_rec"))


class OrganizationLocation(Base):
    __tablename__ = "organization_locations"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    lat: Mapped[Optional[float]] = mapped_column(Float)  # NULL = posição conhecida ausente (nunca inventada)
    lon: Mapped[Optional[float]] = mapped_column(Float)
    location_precision: Mapped[str] = mapped_column(String(24))  # EXACT | MUNICIPALITY_CENTROID | NONE
    geo_quality: Mapped[Optional[str]] = mapped_column(String(20))
    rankable_by_distance: Mapped[bool] = mapped_column(Boolean)
    coord_source: Mapped[str] = mapped_column(String(60))
    data_origin: Mapped[str] = mapped_column(String(12), default="PUBLIC")
    organization: Mapped[Organization] = relationship(back_populates="location")
    __table_args__ = (CheckConstraint("data_origin = 'PUBLIC'", name="ck_orgloc_origin"),
                      CheckConstraint("location_precision IN ('EXACT','MUNICIPALITY_CENTROID','NONE')", name="ck_orgloc_prec"),
                      CheckConstraint("(lat IS NULL AND lon IS NULL AND NOT rankable_by_distance) OR (lat IS NOT NULL AND lon IS NOT NULL)", name="ck_orgloc_coords"))


class OrganizationProfile(SimTraceMixin, Base):
    """Atributos DECLARADOS da ONG (observáveis): SIMULATED enquanto não houver cadastro real; USER_ENTERED quando a própria ONG declarar."""
    __tablename__ = "organization_profiles"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    capacity_min_kg_day: Mapped[Optional[float]] = mapped_column(Float)
    capacity_max_kg_day: Mapped[float] = mapped_column(Float)
    cold_chamber: Mapped[bool] = mapped_column(Boolean)
    open_hour: Mapped[float] = mapped_column(Float)
    close_hour: Mapped[float] = mapped_column(Float)
    open_days_mask: Mapped[int] = mapped_column(SmallInteger)
    accepted_categories: Mapped[list[str]] = mapped_column(ARRAY(String(30)))
    has_fleet: Mapped[bool] = mapped_column(Boolean, default=False)
    fleet_capacity_kg: Mapped[Optional[float]] = mapped_column(Float)
    fleet_refrigerated: Mapped[bool] = mapped_column(Boolean, default=False)
    data_origin: Mapped[str] = mapped_column(String(12))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    organization: Mapped[Organization] = relationship(back_populates="profile")
    __table_args__ = tuple(_origin_checks("orgprof", ("SIMULATED", "USER_ENTERED")))


# ------------------------------------------------------------------ doadores
class Donor(SimTraceMixin, Base):
    __tablename__ = "donors"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    external_id: Mapped[Optional[str]] = mapped_column(String(40))  # id do simulador (D00000); para USER_ENTERED, nulo
    donor_type: Mapped[str] = mapped_column(String(40))
    donor_size: Mapped[Optional[str]] = mapped_column(String(20))
    display_name: Mapped[Optional[str]] = mapped_column(String(160))  # rótulo da pessoa jurídica (opcional; nunca pessoa física)
    municipio_ibge: Mapped[int] = mapped_column(ForeignKey("municipalities.ibge_code"), index=True)
    pickup_days_mask: Mapped[int] = mapped_column(SmallInteger, default=31)
    pickup_start_h: Mapped[float] = mapped_column(Float, default=8.0)
    pickup_end_h: Mapped[float] = mapped_column(Float, default=17.0)
    load_minutes: Mapped[int] = mapped_column(SmallInteger, default=30)
    data_origin: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locations: Mapped[list["DonorLocation"]] = relationship(back_populates="donor")
    __table_args__ = tuple(_origin_checks("donor", ("SIMULATED", "USER_ENTERED"))) + (
        Index("uq_donor_sim_ext", "dataset_version", "external_id", unique=True, postgresql_where=text("external_id IS NOT NULL")),)


class DonorLocation(SimTraceMixin, Base):
    __tablename__ = "donor_locations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    donor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("donors.id"), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    location_precision: Mapped[str] = mapped_column(String(24))
    basis: Mapped[Optional[str]] = mapped_column(String(40))
    data_origin: Mapped[str] = mapped_column(String(12))
    donor: Mapped[Donor] = relationship(back_populates="locations")
    __table_args__ = tuple(_origin_checks("donloc", ("SIMULATED", "USER_ENTERED")))


# ------------------------------------------------------------------ usuários (autenticação mínima)
class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    role: Mapped[str] = mapped_column(String(8))
    label: Mapped[str] = mapped_column(String(80))  # rótulo da conta (não é nome de pessoa)
    donor_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("donors.id"))
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("organizations.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # SHA-256 do token; o token em claro NUNCA é gravado
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)  # conta de demonstração/validação (opera só sobre dados SIMULATED)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (CheckConstraint("role IN ('DONOR','ORG','ADMIN')", name="ck_user_role"),
                      CheckConstraint("(role='DONOR' AND donor_id IS NOT NULL AND organization_id IS NULL) OR (role='ORG' AND organization_id IS NOT NULL AND donor_id IS NULL) "
                                      "OR (role='ADMIN' AND donor_id IS NULL AND organization_id IS NULL)", name="ck_user_binding"))


# ------------------------------------------------------------------ doações
class Donation(SimTraceMixin, Base):
    __tablename__ = "donations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    donor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("donors.id"), index=True)
    data_origin: Mapped[str] = mapped_column(String(12))  # herdada do doador
    status: Mapped[str] = mapped_column(String(24), index=True)
    entry_channel: Mapped[str] = mapped_column(String(24), default="API")  # API | SIMULATOR_IMPORT
    external_id: Mapped[Optional[str]] = mapped_column(String(40))
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    categoria: Mapped[Optional[str]] = mapped_column(ForeignKey("food_categories.code"))
    perecibilidade: Mapped[Optional[str]] = mapped_column(String(40))
    exige_refrigeracao: Mapped[Optional[bool]] = mapped_column(Boolean)
    contem_alergenico: Mapped[bool] = mapped_column(Boolean, default=False)
    quantity_kg: Mapped[Optional[float]] = mapped_column(Float)
    quantity_original: Mapped[Optional[float]] = mapped_column(Float)
    quantity_unit: Mapped[Optional[str]] = mapped_column(String(20))
    validity_days: Mapped[Optional[int]] = mapped_column(Integer)
    expires_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    validity_source: Mapped[Optional[str]] = mapped_column(String(32))
    pickup_days_mask: Mapped[int] = mapped_column(SmallInteger, default=31)
    pickup_start_h: Mapped[float] = mapped_column(Float, default=8.0)
    pickup_end_h: Mapped[float] = mapped_column(Float, default=17.0)
    load_minutes: Mapped[int] = mapped_column(SmallInteger, default=30)
    block_reason: Mapped[Optional[str]] = mapped_column(String(200))
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # por campo: extraído, confiança, final, quem decidiu
    parser_version: Mapped[Optional[str]] = mapped_column(String(60))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())  # "doação registrada"
    confirmed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    imported_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    items: Mapped[list["DonationItem"]] = relationship(back_populates="donation")
    __table_args__ = tuple(_origin_checks("donation", ("SIMULATED", "USER_ENTERED"))) + (
        CheckConstraint("status IN ('PENDING_CONFIRMATION','READY','BLOCKED_EXPIRED','BLOCKED_NO_VALIDITY','MATCHING','MATCHED','NO_MATCH','HISTORICAL')", name="ck_donation_status"),
        Index("uq_donation_sim_ext", "dataset_version", "external_id", unique=True, postgresql_where=text("external_id IS NOT NULL")))


class DonationItem(SimTraceMixin, Base):
    __tablename__ = "donation_items"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    donation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("donations.id"), index=True)
    categoria: Mapped[Optional[str]] = mapped_column(ForeignKey("food_categories.code"))
    produto: Mapped[Optional[str]] = mapped_column(String(80))
    product_name_origin: Mapped[Optional[str]] = mapped_column(String(40))
    quantity: Mapped[Optional[float]] = mapped_column(Float)
    unit: Mapped[Optional[str]] = mapped_column(String(20))
    quantity_kg: Mapped[Optional[float]] = mapped_column(Float)
    data_origin: Mapped[str] = mapped_column(String(12))
    donation: Mapped[Donation] = relationship(back_populates="items")
    __table_args__ = tuple(_origin_checks("ditem", ("SIMULATED", "USER_ENTERED")))


# ------------------------------------------------------------------ matches
class Match(SimTraceMixin, Base):
    __tablename__ = "matches"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    donation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("donations.id"), index=True)
    data_origin: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(12), index=True)
    engine_version: Mapped[str] = mapped_column(String(40))
    model_version: Mapped[str] = mapped_column(String(40))
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB)
    ranking: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)  # candidatas elegíveis, ordenadas, com scores separados e explicação
    eligibility: Mapped[dict[str, Any]] = mapped_column(JSONB)  # regras eliminatórias aplicadas (contagens, amostra de inelegíveis)
    current_org_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("organizations.id"), index=True)
    current_position: Mapped[Optional[int]] = mapped_column(SmallInteger)
    proposal_expires_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), index=True)
    latency_ms: Mapped[dict[str, Any]] = mapped_column(JSONB)
    simulated_clock: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    events: Mapped[list["MatchEvent"]] = relationship(back_populates="match", order_by="MatchEvent.id")
    __table_args__ = tuple(_origin_checks("match", ("SIMULATED", "USER_ENTERED"))) + (
        CheckConstraint("status IN ('PROPOSED','ACCEPTED','COLLECTED','FAILED','EXHAUSTED')", name="ck_match_status"),)


class MatchEvent(Base):
    __tablename__ = "match_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(20))
    from_status: Mapped[Optional[str]] = mapped_column(String(12))
    to_status: Mapped[Optional[str]] = mapped_column(String(12))
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("organizations.id"))
    rank_position: Mapped[Optional[int]] = mapped_column(SmallInteger)
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    actor_type: Mapped[str] = mapped_column(String(10), default="SYSTEM")  # SYSTEM | DONOR | ORG | ADMIN
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    data_origin: Mapped[str] = mapped_column(String(12))
    match: Mapped[Match] = relationship(back_populates="events")
    __table_args__ = (CheckConstraint("data_origin IN ('SIMULATED','USER_ENTERED')", name="ck_mevent_origin"),
                      CheckConstraint("event_type IN ('RANKED','PROPOSED','ACCEPTED','DECLINED','EXPIRED','SKIPPED','EXHAUSTED','COLLECTED','FAILED')", name="ck_mevent_type"))


class CapacityReservation(Base):
    __tablename__ = "capacity_reservations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    reserved_kg: Mapped[float] = mapped_column(Float)
    reservation_date: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10))  # ACTIVE | CONSUMED | RELEASED
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    data_origin: Mapped[str] = mapped_column(String(12))
    __table_args__ = (CheckConstraint("status IN ('ACTIVE','CONSUMED','RELEASED')", name="ck_resv_status"),
                      CheckConstraint("data_origin IN ('SIMULATED','USER_ENTERED')", name="ck_resv_origin"),
                      Index("ix_resv_org_date", "organization_id", "reservation_date", "status"))


class MlPrediction(Base):
    __tablename__ = "ml_predictions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(12))  # PARSER | RANKER
    donation_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("donations.id"), index=True)
    match_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("matches.id"))
    model_name: Mapped[str] = mapped_column(String(60))
    model_version: Mapped[str] = mapped_column(String(80))
    output: Mapped[dict[str, Any]] = mapped_column(JSONB)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    training_data_origin: Mapped[str] = mapped_column(String(40), default="SIMULATED")  # origem dos dados de TREINO do modelo
    subject_data_origin: Mapped[str] = mapped_column(String(12))
    latency_ms: Mapped[Optional[float]] = mapped_column(Float)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (CheckConstraint("kind IN ('PARSER','RANKER')", name="ck_mlp_kind"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))  # sem FK: registra tentativas de contas inexistentes (sem token)
    role: Mapped[Optional[str]] = mapped_column(String(8))
    action: Mapped[str] = mapped_column(String(60))
    resource_type: Mapped[Optional[str]] = mapped_column(String(40))
    resource_id: Mapped[Optional[str]] = mapped_column(String(60))
    outcome: Mapped[str] = mapped_column(String(16))  # OK | AUTH_FAILED | FORBIDDEN | DENIED
    status_code: Mapped[Optional[int]] = mapped_column(SmallInteger)
    method: Mapped[Optional[str]] = mapped_column(String(8))
    path: Mapped[Optional[str]] = mapped_column(String(200))
    client_ip: Mapped[Optional[str]] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # NUNCA contém o token


class BatchAssignmentRun(Base):
    __tablename__ = "batch_assignment_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    data_origin: Mapped[str] = mapped_column(String(12))
    n_lots: Mapped[int] = mapped_column(Integer)
    n_assigned_greedy: Mapped[int] = mapped_column(Integer)
    n_assigned_optimal: Mapped[int] = mapped_column(Integer)
    total_score_greedy: Mapped[float] = mapped_column(Float)
    total_score_optimal: Mapped[float] = mapped_column(Float)
    difference: Mapped[float] = mapped_column(Float)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB)
    __table_args__ = (CheckConstraint("data_origin IN ('SIMULATED','USER_ENTERED')", name="ck_batch_origin"),)
