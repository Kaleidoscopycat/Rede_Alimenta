"""Schemas (Pydantic) da API. Validação estrita de entrada; nenhuma pessoa física é aceita ou retornada."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

Categoria = Literal["HORT_FOLHOSAS", "HORT_RAIZES", "HORT_FRUTOS", "FRUTAS", "PANIFICADOS", "CARNES_PESCADOS", "LATICINIOS_OVOS",
                    "REFEICOES_PRONTAS", "GRAOS_CEREAIS", "INDUSTRIALIZADOS", "BEBIDAS"]


class LoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    categoria: Optional[Categoria] = Field(None, description="Categoria do alimento. Se ausente, é inferida de `descricao_texto`.")
    descricao_texto: Optional[str] = Field(None, max_length=500, description="Texto livre do doador (opcional). Interpretado pelo parser semântico (SIMULADO/treinado em texto simulado).")
    quantidade_kg: float = Field(..., gt=0, le=100_000)
    horas_ate_validade: Optional[float] = Field(None, gt=0, le=24 * 365, description="Horas restantes até o vencimento. Se ausente, é inferido do texto; lotes vencidos são rejeitados.")
    exige_refrigeracao: bool = False
    contem_alergenico: bool = False
    janela_retirada_inicio_h: float = Field(8.0, ge=0, le=24)
    janela_retirada_fim_h: float = Field(17.0, ge=0, le=24)
    tempo_carga_min: float = Field(30.0, ge=0, le=600)
    dias_retirada: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], description="Dias da semana (0=segunda ... 6=domingo)")
    municipio_ibge: Optional[int] = Field(None, ge=1_100_000, le=5_300_000, description="Código IBGE de 7 dígitos (localização por centroide do município).")
    lat: Optional[float] = Field(None, ge=-34.0, le=6.0)
    lon: Optional[float] = Field(None, ge=-75.0, le=-28.0)
    top_n: int = Field(5, ge=1, le=15)

    @model_validator(mode="after")
    def _checks(self):
        if self.municipio_ibge is None and (self.lat is None or self.lon is None):
            raise ValueError("informe `municipio_ibge` ou `lat` e `lon`")
        if self.categoria is None and not self.descricao_texto:
            raise ValueError("informe `categoria` ou `descricao_texto`")
        if any(d < 0 or d > 6 for d in self.dias_retirada) or not self.dias_retirada:
            raise ValueError("`dias_retirada` deve conter inteiros de 0 a 6")
        if self.janela_retirada_fim_h <= self.janela_retirada_inicio_h:
            raise ValueError("janela de retirada inválida")
        return self


class Fator(BaseModel):
    fator: str
    efeito: Literal["aumenta", "reduz", "neutro"]
    impacto: float = Field(description="Variação da probabilidade estimada ao neutralizar o fator (positivo = fator favorece a ONG)")


class RankItem(BaseModel):
    posicao: int
    ong_id: str = Field(description="Identificador pseudonimizado da organização")
    ong_tipo: str
    uf: Optional[str] = None
    municipio_ibge: Optional[int] = None
    dist_km: float
    probabilidade: float = Field(ge=0, le=1, description="P(aceitar e coletar dentro da validade) estimada — modelo treinado em dados SIMULADOS")
    elegivel_regra: bool
    location_precision: str


class Prediction(BaseModel):
    ong_id: str
    probabilidade: float
    recomendado: bool
    limiar_decisao: float


class PredictOut(BaseModel):
    ranking: list[RankItem]
    prediction: Optional[Prediction]
    confidence: float = Field(description="Probabilidade estimada da melhor ONG (NÃO é garantia; ver `aviso`)")
    factors: list[Fator]
    model_version: str
    data_version: str
    data_origin: str
    parsed: Optional[dict] = None
    alertas: list[str] = []
    aviso: str


class ModelInfo(BaseModel):
    model_version: str
    model_name: str
    model_sha256: str
    trained_at: str
    data_version_simulada: str
    data_origin: str
    features: list[str]
    feature_origin: dict[str, str]
    threshold_val: float
    metricas_resumo_teste: dict
    aviso: str
