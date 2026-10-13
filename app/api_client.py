"""Cliente HTTP da API — ÚNICO caminho da interface Streamlit (a interface nunca acessa o banco)."""
from __future__ import annotations

import os
import time
from typing import Any, Callable

import httpx


CAMPOS_PT = {"produto": "nome do alimento", "categoria": "categoria", "quantity": "quantidade de unidades", "unit": "tipo de embalagem", "unit_weight": "peso ou volume por unidade",
             "unit_weight_unit": "unidade de medida", "validade_data": "validade", "validade_mes_ano": "validade (mês/ano)", "exige_refrigeracao": "refrigeração", "description": "descrição",
             "janela_retirada_inicio_h": "início da retirada", "janela_retirada_fim_h": "fim da retirada", "dias_retirada": "dias de retirada", "texto": "texto"}
POR_STATUS = {401: "Sua sessão não foi reconhecida. Confira o código de acesso informado.", 403: "Você não tem permissão para esta ação.", 404: "Não encontramos este registro.",
              410: "Esta função não está mais disponível para o seu perfil.", 429: "Muitas tentativas seguidas. Aguarde um instante e tente de novo.",
              503: "O serviço está temporariamente indisponível. Tente de novo em instantes."}


class ApiError(Exception):
    def __init__(self, status: int, detail: Any):
        self.status, self.detail = status, detail
        super().__init__(f"HTTP {status}: {detail}")

    @property
    def message(self) -> str:
        d = self.detail
        if isinstance(d, dict):
            return str(d.get("mensagem") or d)
        return str(d)

    @property
    def friendly(self) -> str:
        """Mensagem em linguagem simples para a tela (nunca traceback, nunca JSON cru)."""
        d = self.detail
        if isinstance(d, list):  # erro de validação (422): lista de {loc, msg}
            partes = []
            for e in d:
                if isinstance(e, dict):
                    campo = next((CAMPOS_PT.get(str(x)) for x in reversed(e.get("loc", [])) if str(x) in CAMPOS_PT), None)
                    partes.append(f"{campo}: {e.get('msg')}" if campo else str(e.get("msg")))
            return "Confira os dados informados — " + "; ".join(partes) if partes else "Confira os dados informados."
        if self.status >= 500:
            return "Não foi possível concluir agora. Tente novamente em instantes."
        txt = self.message
        if self.status in (401, 403, 404, 410, 429, 503) and not isinstance(d, dict) and (not txt or txt.lower() in ("not found", "forbidden", "unauthorized", "invalid token")):
            return POR_STATUS[self.status]
        return txt or POR_STATUS.get(self.status, "Não foi possível concluir a ação.")


class ApiClient:
    def __init__(self, base_url: str, token: str, http: httpx.Client | None = None, timeout: float = 30.0, wake_max_s: float | None = None,
                 on_wait: Callable[[float], None] | None = None):
        self.token = token
        self.http = http or httpx.Client(base_url=base_url, timeout=timeout)
        self.base = "" if http is not None else ""
        # Plano gratuito do Render: a API hiberna e a 1ª requisição leva ~1 min. Com `wake_max_s` > 0 (env API_WAKE_MAX_S), as CONSULTAS (GET) repetem com espera crescente
        # enquanto a conexão falha ou o proxy responde 502/503/504, avisando a tela por `on_wait`. Padrão 0 = desligado (desenvolvimento e testes).
        self.wake_max_s = float(os.environ.get("API_WAKE_MAX_S", "0")) if wake_max_s is None else wake_max_s
        self.on_wait = on_wait

    def _send(self, method: str, path: str, **kw: Any) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.token}"}
        if method != "GET" or self.wake_max_s <= 0:
            return self.http.request(method, path, headers=headers, **kw)
        t0, delay = time.monotonic(), 2.0
        while True:
            try:
                r = self.http.request(method, path, headers=headers, **kw)
                if r.status_code not in (502, 503, 504) or time.monotonic() - t0 + delay > self.wake_max_s:
                    return r
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError):
                if time.monotonic() - t0 + delay > self.wake_max_s:
                    raise
            if self.on_wait:
                self.on_wait(time.monotonic() - t0)
            time.sleep(delay)
            delay = min(delay * 1.6, 12.0)

    def _req(self, method: str, path: str, **kw: Any) -> Any:
        r = self._send(method, path, **kw)
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text
            raise ApiError(r.status_code, detail)
        return r.json()

    def me(self) -> dict:
        return self._req("GET", "/api/v1/me")

    def model_info(self) -> dict:
        return self._req("GET", "/api/v1/model/info")

    def parse(self, texto: str, donor_id: str | None = None) -> dict:
        """Fluxo antigo (lote único). DESCONTINUADO para DONOR (a API responde 410); ADMIN informa `donor_id`."""
        body: dict = {"texto": texto}
        if donor_id:
            body["donor_id"] = donor_id
        return self._req("POST", "/api/v1/donations/parse", json=body)

    def create_donation(self, payload: dict) -> dict:
        return self._req("POST", "/api/v1/donations", json=payload)

    def get_donation(self, donation_id: str) -> dict:
        return self._req("GET", f"/api/v1/donations/{donation_id}")

    def confirm(self, donation_id: str, payload: dict) -> dict:
        return self._req("PATCH", f"/api/v1/donations/{donation_id}/confirm", json=payload)

    # ---- rascunho e itens (Fase 3 Parte 1 · Etapa A) — fluxo do DONOR
    def create_draft(self, payload: dict | None = None) -> dict:
        return self._req("POST", "/api/v1/donations/drafts", json=payload or {})

    def patch_draft(self, donation_id: str, payload: dict) -> dict:
        return self._req("PATCH", f"/api/v1/donations/{donation_id}/draft", json=payload)

    def add_item(self, donation_id: str, payload: dict) -> dict:
        return self._req("POST", f"/api/v1/donations/{donation_id}/items", json=payload)

    def patch_item(self, donation_id: str, item_id: int, payload: dict) -> dict:
        return self._req("PATCH", f"/api/v1/donations/{donation_id}/items/{item_id}", json=payload)

    def delete_item(self, donation_id: str, item_id: int) -> dict:
        return self._req("DELETE", f"/api/v1/donations/{donation_id}/items/{item_id}")

    def list_items(self, donation_id: str) -> list:
        return self._req("GET", f"/api/v1/donations/{donation_id}/items")

    def parse_preview(self, texto: str, donor_id: str | None = None) -> dict:
        body: dict = {"texto": texto}
        if donor_id:
            body["donor_id"] = donor_id
        return self._req("POST", "/api/v1/donations/items/parse-preview", json=body)

    def items_from_text(self, donation_id: str, texto: str) -> dict:
        return self._req("POST", f"/api/v1/donations/{donation_id}/items/from-text", json={"texto": texto})

    def finalize(self, donation_id: str) -> dict:
        return self._req("POST", f"/api/v1/donations/{donation_id}/finalize")

    def list_donations(self, limit: int = 20, offset: int = 0, status: str | None = None) -> list:
        params: dict = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        return self._req("GET", "/api/v1/donations", params=params)

    # ---- ADMIN (Visão técnica) e dados públicos
    def ranking(self, match_id: str) -> dict:
        return self._req("GET", f"/api/v1/matches/{match_id}/ranking")

    def list_organizations(self, uf: str | None = None, limit: int = 50, offset: int = 0) -> list:
        params: dict = {"limit": limit, "offset": offset}
        if uf:
            params["uf"] = uf
        return self._req("GET", "/api/v1/organizations", params=params)

    def get_organization(self, org_id: str) -> dict:
        return self._req("GET", f"/api/v1/organizations/{org_id}")

    def create_match(self, donation_id: str, top_n: int = 5) -> dict:
        return self._req("POST", "/api/v1/matches", json={"donation_id": donation_id, "top_n": top_n})

    def get_match(self, match_id: str) -> dict:
        return self._req("GET", f"/api/v1/matches/{match_id}")

    def list_matches(self, status: str | None = None, limit: int = 20, offset: int = 0) -> list:
        params: dict = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        return self._req("GET", "/api/v1/matches", params=params)

    def respond(self, match_id: str, accept: bool, note: str | None = None) -> dict:
        return self._req("POST", f"/api/v1/matches/{match_id}/respond", json={"accept": accept, "note": note})

    def outcome(self, match_id: str, result: str) -> dict:
        return self._req("POST", f"/api/v1/matches/{match_id}/outcome", json={"result": result})

    def events(self, match_id: str) -> dict:
        return self._req("GET", f"/api/v1/matches/{match_id}/events")

    def plan_route(self, donation_ids: list[str], vehicle_id: str | None = None, departure_at: str | None = None, safety_margin_h: float | None = None) -> dict:
        body: dict = {"donation_ids": donation_ids}
        if vehicle_id:
            body["vehicle_id"] = vehicle_id
        if departure_at:
            body["departure_at"] = departure_at
        if safety_margin_h is not None:
            body["safety_margin_h"] = safety_margin_h
        return self._req("POST", "/api/v1/routes/plan", json=body)

    def get_route(self, route_id: str) -> dict:
        return self._req("GET", f"/api/v1/routes/{route_id}")

    # ---- Dashboard do ADMIN (Fase 3 Parte 2 · Etapa A): /api/v1/admin/stats/* (cada consulta é auditada pela API)
    def stats(self, tela: str, **params: Any) -> dict:
        """GET /api/v1/admin/stats/<tela> com filtros (valores vazios são descartados)."""
        q = {k: v for k, v in params.items() if v not in (None, "", [])}
        return self._req("GET", f"/api/v1/admin/stats/{tela}", params=q)

    def logistics_strategies(self, n_lots: int, seed: int, raio_km: float, tempo_solver_s: int = 1) -> dict:
        return self._req("POST", "/api/v1/admin/stats/logistics/strategies", json={"n_lots": n_lots, "seed": seed, "raio_km": raio_km, "tempo_solver_s": tempo_solver_s})

    def predict(self, payload: dict) -> dict:
        return self._req("POST", "/api/v1/predictions", json=payload)
