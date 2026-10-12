"""Regras PURAS dos itens de uma doação (Fase 3 Parte 1): conversão para kg, validade (data ou mês/ano) e rótulos de premissa.

Conversão para kg (seção 2.3 do prompt):
  * item = unidades × peso (ou volume) da embalagem, convertido para kg;
  * kg e g são massa informada;
  * litro/ml → kg usa a massa por litro da categoria na taxonomia (`unit_mass_kg.litro`, PREMISSA do projeto SEM FONTE) ou, se a categoria não a tiver,
    a densidade padrão configurada (DONATION_DEFAULT_DENSITY_KG_L, 1,0 kg/L, PREMISSA SEM FONTE) — sempre sinalizado como "peso estimado";
  * massa unitária por tipo de embalagem (pacote, caixa, unidade...) da taxonomia é PREMISSA SEM FONTE e só é usada como SUGESTÃO do parser de texto, nunca em silêncio.
Nunca preenche peso em silêncio: sem peso por unidade, `quantity_kg` fica None."""
from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass

from core.settings import DONATION, TZ

MASS_TO_KG = {"kg": 1.0, "g": 0.001}
VOLUME_TO_L = {"l": 1.0, "ml": 0.001}
WEIGHT_UNITS = tuple(MASS_TO_KG) + tuple(VOLUME_TO_L)
BASIS_MASS, BASIS_VOLUME, BASIS_CATEGORY = "MASSA_INFORMADA", "VOLUME_CONVERTIDO", "MASSA_UNITARIA_CATEGORIA"
PREMISSE_TXT = "premissa sem fonte"
PREMISE_SOURCE = "taxonomia v0.2 do projeto (premissa SEM fonte externa)"
MONTH_YEAR_RE = re.compile(r"^(?:(0[1-9]|1[0-2])/(\d{4})|(\d{4})-(0[1-9]|1[0-2]))$")


@dataclass(frozen=True)
class ItemWeight:
    quantity_kg: float | None
    basis: str | None
    estimated: bool
    note: str | None
    kg_per_unit: float | None


def volume_density(categoria: str | None, unit_mass: dict[str, float] | None) -> tuple[float, str]:
    """kg por litro e a descrição da premissa usada."""
    um = unit_mass or {}
    if "litro" in um:
        return float(um["litro"]), f"{float(um['litro']):g} kg/L para a categoria {categoria} ({PREMISSE_TXT})"
    return DONATION.default_density_kg_per_l, f"{DONATION.default_density_kg_per_l:g} kg/L (a categoria {categoria} não tem massa por litro; densidade padrão: premissa sem fonte)"




def weight_per_unit(unit_weight: float | None, unit: str | None, categoria: str | None, unit_mass: dict[str, float] | None) -> tuple[float | None, str | None, str | None]:
    """(kg por unidade/embalagem, base, nota). Base ∈ MASSA_INFORMADA | VOLUME_CONVERTIDO; None se o peso não foi informado."""
    if unit_weight is None or unit is None:
        return None, None, None
    if unit in MASS_TO_KG:
        return float(unit_weight) * MASS_TO_KG[unit], BASIS_MASS, None
    if unit in VOLUME_TO_L:
        dens, why = volume_density(categoria, unit_mass)
        return float(unit_weight) * VOLUME_TO_L[unit] * dens, BASIS_VOLUME, f"peso estimado: volume convertido em kg com {why}"
    raise ValueError(f"unidade de peso/volume inválida: {unit!r} (use kg, g, l ou ml)")


def item_weight(unit_count: float | None, unit_weight: float | None, unit: str | None, categoria: str | None, unit_mass: dict[str, float] | None) -> ItemWeight:
    kg_u, basis, note = weight_per_unit(unit_weight, unit, categoria, unit_mass)
    if kg_u is None or unit_count is None:
        return ItemWeight(None, None, False, "peso por unidade ou quantidade de unidades não informado", kg_u)
    total = round(float(unit_count) * kg_u, 6)
    if total > DONATION.max_total_kg:
        raise ValueError(f"peso total do item acima do limite de {DONATION.max_total_kg:g} kg")
    return ItemWeight(total, basis, basis != BASIS_MASS, note, kg_u)


def category_unit_mass(packaging: str | None, categoria: str | None, unit_mass: dict[str, float] | None) -> float | None:
    """Massa (kg) de uma embalagem pela taxonomia — PREMISSA SEM FONTE; usada só para SUGESTÃO do parser (item fica pendente)."""
    um = unit_mass or {}
    if packaging and packaging in um:
        return float(um[packaging])
    return None


# ---------------------------------------------------------------------------------------------------- validade
def last_day_of_month(year: int, month: int) -> dt.date:
    return dt.date(year, month, calendar.monthrange(year, month)[1])


def parse_month_year(text: str) -> dt.date | None:
    """'MM/AAAA' ou 'AAAA-MM' → ÚLTIMO dia do mês (regra definida pela equipe; é a leitura MENOS restritiva: a validade real pode ser anterior, por isso o doador é avisado e o campo fica pendente)."""
    m = MONTH_YEAR_RE.match(text.strip())
    if not m:
        return None
    month, year = (int(m.group(1)), int(m.group(2))) if m.group(1) else (int(m.group(4)), int(m.group(3)))
    return last_day_of_month(year, month)


def end_of_day(d: dt.date) -> dt.datetime:
    """Mesma convenção das regras da Fase 2: a validade vale até 23:59:59 (America/Sao_Paulo) do dia informado."""
    return dt.datetime.combine(d, dt.time(23, 59, 59), tzinfo=TZ)


def days_until(d: dt.date, today: dt.date) -> int:
    return (d - today).days


def validity_note(precision: str | None, expires_at: dt.datetime | None) -> str | None:
    if precision == "MONTH" and expires_at is not None:
        return f"Só mês/ano informados: usamos o último dia do mês ({expires_at.astimezone(TZ).strftime('%d/%m/%Y')}); a validade real pode ser anterior — confirme a data exata se possível."
    return None
