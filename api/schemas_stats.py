"""Modelos de resposta do dashboard do ADMIN (/api/v1/admin/stats/...). Toda linha numérica carrega `data_origin` + `selo`; valores de origens diferentes NUNCA são somados num mesmo número.

Selos (AGENTS.md / seção 3 do prompt da Fase 3 Parte 2):
  PÚBLICO = data_origin PUBLIC (histórico de fonte oficial) · SIMULADO = data_origin SIMULATED (simulador documentado) · MEDIDO = data_origin USER_ENTERED (entrada real na plataforma)."""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Origin = Literal["PUBLIC", "SIMULATED", "USER_ENTERED"]
SELOS: dict[str, str] = {"PUBLIC": "PÚBLICO", "SIMULATED": "SIMULADO", "USER_ENTERED": "MEDIDO"}
NIVEIS = ("macro", "uf", "municipio")


def selo(origin: str) -> str:
    return SELOS.get(origin, origin)


class Rot(BaseModel):
    """Linha rotulada pela origem do dado."""
    data_origin: Origin
    selo: str


class Premissa(BaseModel):
    kg_por_refeicao: float
    descricao: str


# ------------------------------------------------------------------------------------------------ overview
class CatalogoPublico(Rot):
    ongs_catalogadas: int
    bancos_de_alimentos_rbba: int
    municipios_cobertos: int
    ufs_cobertas: int
    registros_publicos_processados: int
    fontes_publicas: int
    ultima_atualizacao_datasets: Optional[dt.datetime]
    nota: str


class DoacaoBloco(Rot):
    n_doacoes: int
    kg: float
    refeicoes_estimadas: float
    titulo: str
    legenda: str


class MatchBloco(Rot):
    n_matches: int
    propostas: int
    aceitas: int
    recusadas: int
    expiradas: int
    coletadas: int
    taxa_aceite: Optional[float] = Field(None, description="aceites ÷ (aceites + recusas + expiradas): propostas com desfecho")


class TempoMatchBloco(Rot):
    n_matches: int
    registro_ate_primeira_proposta_s: Optional[float]
    proposta_ate_resposta_s: Optional[float]
    registro_ate_aceite_s: Optional[float]
    origem_texto: str


class DoadoresBloco(Rot):
    n_doadores: int


class LatenciaBloco(Rot):
    n: int
    media_ms: Optional[float]
    p50_ms: Optional[float]
    p95_ms: Optional[float]


class IaResumo(BaseModel):
    disponivel: bool
    rotulo: str
    versao: Optional[str] = None
    mrr: Optional[float] = None
    top1_hit_rate: Optional[float] = None
    top3_hit_rate: Optional[float] = None
    mrr_baseline_ong_mais_proxima: Optional[float] = None
    mrr_baseline_regra: Optional[float] = None
    acc_categoria_parser: Optional[float] = None
    nota_nomes: str


class SegurancaResumo(BaseModel):
    total_mitigadas_comprovadas: int
    ferramentas_comprovadas: list[str]
    pendencias: list[str]
    data_origin: Origin = "PUBLIC"
    selo: str = "PÚBLICO"


class OverviewOut(BaseModel):
    premissa: Premissa
    catalogo: CatalogoPublico
    doadores: list[DoadoresBloco]
    doacoes_ofertadas: list[DoacaoBloco]
    doacoes_coletadas: list[DoacaoBloco]
    matches: list[MatchBloco]
    tempo_match: list[TempoMatchBloco]
    latencia_ranking: list[LatenciaBloco]
    ia: IaResumo
    seguranca: SegurancaResumo
    nenhuma_doacao_real: bool
    aviso_doacao_real: Optional[str]
    filtros_aplicados: dict[str, Any]


# ------------------------------------------------------------------------------------------------ doações e matches
class SerieMes(Rot):
    mes: str
    n_doacoes: int
    kg: float
    refeicoes_estimadas: float


class ContagemRot(Rot):
    chave: str
    n: int
    kg: Optional[float] = None


class DoacoesMatchesOut(BaseModel):
    titulo: str
    legenda: str
    serie_mensal: list[SerieMes]
    por_status: list[ContagemRot]
    por_categoria: list[ContagemRot]
    matches_por_status: list[ContagemRot]
    ciclo_do_match: list[ContagemRot]
    latencia_ranking: list[LatenciaBloco]
    premissa: Premissa
    nenhuma_doacao_real: bool


class RegiaoRow(Rot):
    regiao: str
    uf: Optional[str] = None
    municipio_ibge: Optional[int] = None
    nome: Optional[str] = None
    n_doacoes: int
    kg: float
    refeicoes_estimadas: float


class RefeicoesRegiaoOut(BaseModel):
    titulo: str
    legenda: str
    nivel: Literal["macro", "uf", "municipio"]
    base: Literal["ofertado", "coletado"]
    premissa: Premissa
    linhas: list[RegiaoRow]
    nenhuma_doacao_real: bool


# ------------------------------------------------------------------------------------------------ mapa
class PontoMunicipio(BaseModel):
    municipio_ibge: int
    nome: str
    uf: str
    lat: float
    lon: float
    n: int
    kg: Optional[float] = None
    refeicoes_estimadas: Optional[float] = None
    data_origin: Origin
    selo: str
    location_precision: str = "MUNICIPALITY_CENTROID"


class PontoOng(BaseModel):
    ong_id: str
    ong_tipo: str
    uf: Optional[str]
    lat: float
    lon: float
    location_precision: str
    data_origin: Origin = "PUBLIC"
    selo: str = "PÚBLICO"


class ParadaRota(BaseModel):
    seq: int
    tipo: str
    lat: float
    lon: float
    location_precision: str
    doador: Optional[str] = None
    chegada_planejada: Optional[dt.datetime] = None


class RotaMapa(Rot):
    id: str
    ong_id: str
    algoritmo: str
    status: str
    total_km_est: Optional[float]
    total_minutos_est: Optional[int]
    distancia_base: str
    paradas: list[ParadaRota]
    aviso_distancia: Optional[str]


class MapaOut(BaseModel):
    titulo: str
    legenda: str
    ongs_por_municipio: list[PontoMunicipio]
    ongs_pontos: list[PontoOng]
    ongs_pontos_truncado: bool
    doadores_por_municipio: list[PontoMunicipio]
    doacoes_por_municipio: list[PontoMunicipio]
    rotas: list[RotaMapa]
    aviso_localizacao: str
    sem_mapa_base: str


# ------------------------------------------------------------------------------------------------ organizações, doadores, dados públicos, territorial
class OrgLinha(BaseModel):
    ong_id: str
    ong_tipo: str
    uf: Optional[str]
    municipio_ibge: Optional[int]
    municipio: Optional[str]
    location_precision: str
    platform_status: str
    licenca: str
    perfil_origin: Optional[str]
    capacidade_max_kg_dia: Optional[float]
    camara_fria: Optional[bool]
    tem_frota: Optional[bool]
    data_origin: Origin = "PUBLIC"
    selo: str = "PÚBLICO"


class OrganizacoesOut(BaseModel):
    titulo: str
    legenda: str
    total: int
    por_tipo: list[ContagemRot]
    por_uf: list[ContagemRot]
    por_precisao_localizacao: list[ContagemRot]
    por_status_plataforma: list[ContagemRot]
    perfil_declarado: list[ContagemRot]
    linhas: list[OrgLinha]
    limit: int
    offset: int


class DoadorLinha(Rot):
    donor_id: str
    external_id: Optional[str]
    donor_type: str
    donor_size: Optional[str]
    uf: str
    municipio_ibge: int
    municipio: str
    n_doacoes: int
    kg: float


class DoadoresOut(BaseModel):
    titulo: str
    legenda: str
    total: list[ContagemRot]
    por_tipo: list[ContagemRot]
    por_porte: list[ContagemRot]
    linhas: list[DoadorLinha]
    limit: int
    offset: int
    nenhuma_doacao_real: bool


class FontePublica(BaseModel):
    id: str
    nome: str
    organizacao: Optional[str]
    url: Optional[str]
    licenca: str
    revisao: str
    uso_comercial: str
    liberada_para_publicacao: bool
    n_registros: Optional[int]
    versao: Optional[str]
    ingerida_em: Optional[dt.datetime]
    atualizada_na_fonte: Optional[str]
    data_origin: Origin = "PUBLIC"
    selo: str = "PÚBLICO"


class DadosPublicosOut(BaseModel):
    titulo: str
    legenda: str
    fontes: list[FontePublica]
    registros_processados: int
    ultima_atualizacao: Optional[dt.datetime]
    indicadores_por_codigo: list[dict[str, Any]]
    aviso_licenca: str


class TerritorialRow(BaseModel):
    chave: str
    nome: Optional[str] = None
    uf: Optional[str] = None
    valor: float
    por_100mil_habitantes: Optional[float] = None
    populacao: Optional[float] = None


class TerritorialOut(BaseModel):
    titulo: str
    legenda: str
    codigo: str
    unidade: Optional[str]
    periodo_referencia: Optional[str]
    nivel: Literal["uf", "municipio"]
    codigos_disponiveis: list[dict[str, Any]]
    linhas: list[TerritorialRow]
    data_origin: Origin = "PUBLIC"
    selo: str = "PÚBLICO"
    nota: str


# ------------------------------------------------------------------------------------------------ IA, segurança, logística
class AiOut(BaseModel):
    ranker: dict[str, Any]
    parser: dict[str, Any]
    engine: dict[str, Any]
    lote_misto: dict[str, Any]
    limitacoes: list[dict[str, str]]
    glossario: dict[str, str]
    datasets: list[dict[str, Any]]
    rotulo: str


class SecurityOut(BaseModel):
    relatorios: dict[str, Any]
    sistema: dict[str, Any]


class StrategiesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n_lots: int = Field(8, ge=2, le=24, description="Quantidade de lotes SIMULADOS no cenário")
    seed: int = Field(20261012, ge=0, le=2**31 - 1)
    raio_km: float = Field(40.0, ge=5, le=150, description="Raio (km) em torno da âncora para escolher doadores")
    tempo_solver_s: int = Field(1, ge=1, le=3)
