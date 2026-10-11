"""Estado compartilhado da aplicação: ranker (modelo da Fase 1), índice de ONGs em memória, motor de match e parser semântico."""
from __future__ import annotations

import logging
import threading
from typing import Any

from sqlalchemy import select, text

from api.parsing import ParserService
from api.service import Ranker
from database import models as m
from database.session import get_engine, session_scope
from match.engine import MatchEngine
from match.index import OrgIndex, load_org_index

log = logging.getLogger("api.state")


class AppState:
    def __init__(self) -> None:
        self.ranker: Ranker | None = None
        self.engine: MatchEngine | None = None
        self.index: OrgIndex | None = None
        self.parser: ParserService | None = None
        self.unit_mass: dict[str, dict[str, float]] = {}
        self.cat_perecibilidade: dict[str, str] = {}
        self.error: str | None = None
        self.lock = threading.Lock()

    def load(self) -> None:
        try:
            self.parser = ParserService()
            self.reload_index()
        except Exception as e:  # /ready reporta a falha
            self.error = f"{type(e).__name__}: {e}"
            log.exception("falha na inicialização")

    def reload_index(self) -> None:
        with self.lock:
            idx = load_org_index(get_engine())
            ranker = Ranker(orgs=idx.orgs, terr=idx.terr, load_parser=False)
            ranker.parser = self.parser.parser if self.parser else None  # predictions com descricao_texto
            self.index, self.ranker, self.engine = idx, ranker, MatchEngine(ranker, idx)
            with session_scope() as s:
                cats = list(s.scalars(select(m.FoodCategory)))
                self.unit_mass = {c.code: dict(c.unit_mass_kg or {}) for c in cats}
                self.cat_perecibilidade = {c.code: c.perecibilidade for c in cats}
            self.error = None

    def ready(self) -> tuple[bool, str]:
        if self.error:
            return False, self.error
        if not (self.ranker and self.engine and self.parser and self.index):
            return False, "carregando"
        try:
            with get_engine().connect() as c:
                c.execute(text("select 1"))
        except Exception as e:
            return False, f"banco indisponível: {type(e).__name__}"
        return True, "ok"


STATE = AppState()
