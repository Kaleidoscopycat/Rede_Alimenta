"""Cliente HTTP da API — ÚNICO caminho da interface Streamlit (a interface nunca acessa o banco)."""
from __future__ import annotations

from typing import Any

import httpx


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


class ApiClient:
    def __init__(self, base_url: str, token: str, http: httpx.Client | None = None, timeout: float = 30.0):
        self.token = token
        self.http = http or httpx.Client(base_url=base_url, timeout=timeout)
        self.base = "" if http is not None else ""

    def _req(self, method: str, path: str, **kw: Any) -> Any:
        r = self.http.request(method, path, headers={"Authorization": f"Bearer {self.token}"}, **kw)
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

    def parse(self, texto: str) -> dict:
        return self._req("POST", "/api/v1/donations/parse", json={"texto": texto})

    def create_donation(self, payload: dict) -> dict:
        return self._req("POST", "/api/v1/donations", json=payload)

    def get_donation(self, donation_id: str) -> dict:
        return self._req("GET", f"/api/v1/donations/{donation_id}")

    def confirm(self, donation_id: str, payload: dict) -> dict:
        return self._req("PATCH", f"/api/v1/donations/{donation_id}/confirm", json=payload)

    def create_match(self, donation_id: str, top_n: int = 5) -> dict:
        return self._req("POST", "/api/v1/matches", json={"donation_id": donation_id, "top_n": top_n})

    def get_match(self, match_id: str) -> dict:
        return self._req("GET", f"/api/v1/matches/{match_id}")

    def list_matches(self, status: str | None = None) -> list:
        return self._req("GET", "/api/v1/matches", params={"status": status} if status else None)

    def respond(self, match_id: str, accept: bool, note: str | None = None) -> dict:
        return self._req("POST", f"/api/v1/matches/{match_id}/respond", json={"accept": accept, "note": note})

    def outcome(self, match_id: str, result: str) -> dict:
        return self._req("POST", f"/api/v1/matches/{match_id}/outcome", json={"result": result})

    def events(self, match_id: str) -> dict:
        return self._req("GET", f"/api/v1/matches/{match_id}/events")
