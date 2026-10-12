"""Entradas da API de rascunho e itens (Fase 3 Parte 1). Estritas (extra=forbid)."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal, Optional

from pydantic import Field, model_validator

from api.schemas import Categoria
from api.schemas_v2 import Strict

PESO_UNIDADES = Literal["kg", "g", "l", "ml"]
EMB = r"^[a-zà-úA-ZÀ-Ú ]{2,20}$"


class DraftIn(Strict):
    donor_id: Optional[uuid.UUID] = Field(None, description="Somente ADMIN")
    texto: Optional[str] = Field(None, min_length=3, max_length=2000, description="Opcional: texto livre com vários itens (vira SUGESTÕES a confirmar)")
    contem_alergenico: bool = False
    janela_retirada_inicio_h: Optional[float] = Field(None, ge=0, le=24)
    janela_retirada_fim_h: Optional[float] = Field(None, ge=0, le=24)
    tempo_carga_min: Optional[int] = Field(None, ge=0, le=600)
    dias_retirada: Optional[list[int]] = None

    @model_validator(mode="after")
    def _chk(self):
        if self.dias_retirada is not None and (not self.dias_retirada or any(d < 0 or d > 6 for d in self.dias_retirada)):
            raise ValueError("dias_retirada deve conter inteiros de 0 a 6")
        return self


class DraftPatch(Strict):
    contem_alergenico: Optional[bool] = None
    janela_retirada_inicio_h: Optional[float] = Field(None, ge=0, le=24)
    janela_retirada_fim_h: Optional[float] = Field(None, ge=0, le=24)
    tempo_carga_min: Optional[int] = Field(None, ge=0, le=600)
    dias_retirada: Optional[list[int]] = None

    @model_validator(mode="after")
    def _chk(self):
        if self.dias_retirada is not None and (not self.dias_retirada or any(d < 0 or d > 6 for d in self.dias_retirada)):
            raise ValueError("dias_retirada deve conter inteiros de 0 a 6")
        return self


class ItemIn(Strict):
    produto: str = Field(min_length=2, max_length=80)
    description: Optional[str] = Field(None, max_length=160)
    categoria: Categoria
    quantity: float = Field(gt=0, le=100_000, description="Número de unidades/embalagens")
    unit: Optional[str] = Field(None, pattern=EMB, description="Tipo de embalagem (pacote, caixa, garrafa, unidade...)")
    unit_weight: float = Field(gt=0, le=100_000, description="Peso ou volume de CADA unidade/embalagem")
    unit_weight_unit: PESO_UNIDADES
    validade_data: Optional[dt.date] = None
    validade_mes_ano: Optional[str] = Field(None, pattern=r"^(?:(0[1-9]|1[0-2])/\d{4}|\d{4}-(0[1-9]|1[0-2]))$", description="MM/AAAA: usamos o último dia do mês")
    exige_refrigeracao: Optional[bool] = None

    @model_validator(mode="after")
    def _chk(self):
        if self.validade_data is not None and self.validade_mes_ano is not None:
            raise ValueError("informe `validade_data` OU `validade_mes_ano`")
        return self


class ItemPatch(Strict):
    produto: Optional[str] = Field(None, min_length=2, max_length=80)
    description: Optional[str] = Field(None, max_length=160)
    categoria: Optional[Categoria] = None
    quantity: Optional[float] = Field(None, gt=0, le=100_000)
    unit: Optional[str] = Field(None, pattern=EMB)
    unit_weight: Optional[float] = Field(None, gt=0, le=100_000)
    unit_weight_unit: Optional[PESO_UNIDADES] = None
    validade_data: Optional[dt.date] = None
    validade_mes_ano: Optional[str] = Field(None, pattern=r"^(?:(0[1-9]|1[0-2])/\d{4}|\d{4}-(0[1-9]|1[0-2]))$")
    exige_refrigeracao: Optional[bool] = None
    accept_fields: list[Literal["categoria", "quantidade", "peso_por_unidade", "validade", "exige_refrigeracao"]] = Field(
        default_factory=list, description="Campos sugeridos pelo texto que o doador aceita como estão")
    confirm_item: bool = Field(False, description="Confirma o item como um todo (após conferir os campos)")

    @model_validator(mode="after")
    def _chk(self):
        if self.validade_data is not None and self.validade_mes_ano is not None:
            raise ValueError("informe `validade_data` OU `validade_mes_ano`")
        return self


class TextIn(Strict):
    texto: str = Field(min_length=3, max_length=2000)
    donor_id: Optional[uuid.UUID] = Field(None, description="Somente ADMIN (pré-visualização)")
