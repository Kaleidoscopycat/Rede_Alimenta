"""Endurecimento mínimo para URL pública (Fase 3 Parte 2 · Etapa B). Ativo conforme `APP_ENV`; a Fase 4 completa o resto (rate limit global, rotação de tokens, WAF).

* Cabeçalhos de segurança nas respostas da API (somente production).
* CORS restrito às origens da variável CORS_ALLOW_ORIGINS (lista separada por vírgulas; vazio ⇒ nenhuma origem de navegador; o frontend Streamlit chama a API pelo servidor).
* Limite simples, EM MEMÓRIA, de tentativas de autenticação INVÁLIDAS por IP (a instância gratuita do Render é única; reinicia ⇒ zera; não protege contra DDoS).
* IP do cliente atrás do proxy da plataforma: só com TRUST_PROXY_HEADERS=true usa o ÚLTIMO elemento de X-Forwarded-For (o acrescentado pelo proxy confiável; os anteriores podem ser forjados pelo cliente)."""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from typing import Any

SECURITY_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"no-referrer",
    b"cache-control": b"no-store",
    b"content-security-policy": b"default-src 'none'; frame-ancestors 'none'",
    b"strict-transport-security": b"max-age=31536000; includeSubDomains",  # o TLS é terminado pela plataforma; o cabeçalho só vale sobre HTTPS
    b"permissions-policy": b"geolocation=(), microphone=(), camera=()",
}


class SecurityHeadersMiddleware:
    """ASGI puro: acrescenta os cabeçalhos acima a toda resposta HTTP (sem sobrescrever os que a rota já definiu)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                headers += [(k, v) for k, v in SECURITY_HEADERS.items() if k not in present]
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)


def cors_origins() -> list[str]:
    return [o.strip().rstrip("/") for o in os.environ.get("CORS_ALLOW_ORIGINS", "").split(",") if o.strip() and o.strip() != "*"]


def trust_proxy_headers() -> bool:
    return os.environ.get("TRUST_PROXY_HEADERS", "false").strip().lower() in ("1", "true", "yes")


def client_ip(request: Any) -> str:
    if trust_proxy_headers():
        xff = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-1][:64]
    return request.client.host if request.client else "-"


class AuthFailureLimiter:
    """Janela deslizante por IP: após `max_failures` falhas em `window_s` segundos o IP recebe 429 até a janela esvaziar. Memória limitada (`max_keys`)."""

    def __init__(self, max_failures: int | None = None, window_s: int | None = None, max_keys: int = 5000) -> None:
        self.max_failures = int(os.environ.get("AUTH_MAX_FAILURES", 20)) if max_failures is None else max_failures
        self.window_s = int(os.environ.get("AUTH_WINDOW_SECONDS", 300)) if window_s is None else window_s
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, q: deque[float], now: float) -> None:
        while q and now - q[0] > self.window_s:
            q.popleft()

    def blocked(self, ip: str, now: float | None = None) -> int:
        """Segundos até poder tentar de novo (0 = liberado)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits.get(ip)
            if not q:
                return 0
            self._prune(q, now)
            if len(q) >= self.max_failures:
                return max(1, int(self.window_s - (now - q[0])))
            if not q:
                self._hits.pop(ip, None)
            return 0

    def fail(self, ip: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            if ip not in self._hits and len(self._hits) >= self.max_keys:  # descarta o mais antigo para não crescer sem limite
                self._hits.pop(next(iter(self._hits)), None)
            q = self._hits[ip]
            self._prune(q, now)
            q.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


AUTH_LIMITER = AuthFailureLimiter()
