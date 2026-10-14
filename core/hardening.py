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


# ============================================================================================ Rate limit GLOBAL por requisição (Fase 4 · Etapa B)
# Por INSTÂNCIA e EM MEMÓRIA (o plano gratuito do Render roda uma instância; reinício/hibernação zera os contadores). Não é distribuído:
# ao escalar para várias instâncias cada uma contaria sozinha ⇒ o limite efetivo seria N× maior; aí o correto é um contador compartilhado (Redis) ou um gateway/WAF na frente.
#
# Chave do limite (decisão de projeto): o frontend Streamlit chama a API A PARTIR DO SERVIDOR dele, então todas as pessoas da demonstração chegam com o MESMO IP; um limite só por IP
# derrubaria a defesa inteira. Por isso: (1) cabeçalho `Authorization: Bearer rai_…` com formato válido ⇒ chave = SHA-256 do token (o token em si nunca é guardado nem registrado);
# (2) sem token / formato inválido ⇒ chave = IP (mesma extração do limitador de autenticação, respeitando TRUST_PROXY_HEADERS); (3) um TETO por IP, bem folgado, contra quem gira tokens de formato
# válido para criar chaves novas (tokens inexistentes já caem no limitador de falhas de autenticação, que bloqueia após 20 falhas em 300 s).
#
# Padrões (generosos): a tela do doador e da ONG se atualiza a cada 5 s (`st.fragment(run_every=5)` em app/page_donor.py e app/page_org.py), com poucas chamadas por atualização
# (≈ 12 atualizações/min × até 3 chamadas ≈ 36/min por sessão aberta — estimativa de projeto, não medição). 1.200/min por token ≈ 20 req/s ≈ mais de 30 sessões abertas com o MESMO token.
# Sem token: 240/min por IP (a API não serve nada útil sem token). Teto por IP: 6.000/min (≈ 100 req/s), muito acima do uso da demonstração e abaixo do que esgotaria a CPU do plano gratuito.
# Janela FIXA (contador por chave e janela): barata e previsível; permite até 2× o limite numa virada de janela — aceitável para este objetivo (mitigar abuso, não medir cota).
import hashlib  # noqa: E402
import logging  # noqa: E402
import re  # noqa: E402
from dataclasses import dataclass  # noqa: E402

_TOKEN_HEADER_RE = re.compile(r"^Bearer (rai_[A-Za-z0-9_\-]{20,128})$")
RATE_LIMIT_EXEMPT_PATHS = frozenset({"/health", "/ready"})  # health checks do Render nunca são limitados
RATE_LIMIT_MESSAGE = "muitas requisições; aguarde e tente novamente"
_log = logging.getLogger("api.ratelimit")


def _env_int(name: str, default: int, minimo: int = 1) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        v = int(raw)
    except ValueError:
        raise RuntimeError(f"{name} deve ser um inteiro") from None
    if v < minimo:
        raise RuntimeError(f"{name} deve ser >= {minimo}")
    return v


@dataclass(frozen=True)
class RateLimitConfig:
    enabled: bool = True
    window_s: int = 60
    token_max: int = 1200
    ip_max: int = 240
    ip_ceiling_max: int = 6000
    max_keys: int = 10000

    @classmethod
    def from_env(cls) -> "RateLimitConfig":
        enabled = os.environ.get("RATE_LIMIT_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")
        return cls(enabled=enabled, window_s=_env_int("RATE_LIMIT_WINDOW_SECONDS", 60), token_max=_env_int("RATE_LIMIT_TOKEN_MAX", 1200), ip_max=_env_int("RATE_LIMIT_IP_MAX", 240),
                   ip_ceiling_max=_env_int("RATE_LIMIT_IP_CEILING_MAX", 6000), max_keys=_env_int("RATE_LIMIT_MAX_KEYS", 10000, 100))


class FixedWindowCounter:
    """Contador por chave em janela fixa; thread-safe; memória limitada (varredura preguiçosa de janelas vencidas + teto de chaves, descartando as mais antigas)."""

    def __init__(self, window_s: int = 60, max_keys: int = 10000) -> None:
        self.window_s, self.max_keys = window_s, max_keys
        self._d: dict[str, list] = {}  # chave → [início_da_janela, contagem, bloqueio_já_logado]
        self._lock = threading.Lock()
        self._last_sweep = 0.0

    def _sweep(self, now: float) -> None:
        if now - self._last_sweep < self.window_s:
            return
        self._last_sweep = now
        for k in [k for k, v in self._d.items() if now - v[0] >= self.window_s]:
            del self._d[k]

    def hit(self, key: str, limit: int, now: float | None = None) -> tuple[bool, int, bool]:
        """Conta uma requisição. Devolve (permitida, segundos_até_a_janela_virar, primeiro_bloqueio_desta_janela)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            self._sweep(now)
            b = self._d.get(key)
            if b is None or now - b[0] >= self.window_s:
                b = self._d[key] = [now, 0, False]
                while len(self._d) > self.max_keys:  # teto de memória: descarta as chaves mais antigas (ordem de inserção); a recém-criada é a última
                    self._d.pop(next(iter(self._d)))
            b[1] += 1
            if b[1] <= limit:
                return True, 0, False
            first = not b[2]
            b[2] = True
            return False, max(1, int(self.window_s - (now - b[0]) + 0.999)), first

    def size(self) -> int:
        with self._lock:
            return len(self._d)

    def clear(self) -> None:
        with self._lock:
            self._d.clear()


class RateLimitState:
    """Config + contadores + estatística (visível ao ADMIN em /api/v1/admin/stats/security). Nunca guarda token."""

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self.cfg = config or RateLimitConfig.from_env()
        self.by_key = FixedWindowCounter(self.cfg.window_s, self.cfg.max_keys)
        self.by_ip = FixedWindowCounter(self.cfg.window_s, self.cfg.max_keys)
        self.blocked_total = {"por_credencial": 0, "por_ip": 0}
        self._lock = threading.Lock()

    def check(self, authorization: str | None, ip: str, now: float | None = None) -> tuple[bool, int, str, bool]:
        """(permitida, retry_after, tipo_de_chave 'token'|'ip', primeiro_bloqueio)."""
        c = self.cfg
        m = _TOKEN_HEADER_RE.match(authorization or "")
        if m:
            kind, key, limit = "token", "t:" + hashlib.sha256(m.group(1).encode()).hexdigest(), c.token_max
        else:
            kind, key, limit = "ip", "i:" + ip, c.ip_max
        ok_ip, retry_ip, first_ip = self.by_ip.hit(ip, c.ip_ceiling_max, now)  # teto por IP vale para todos
        ok, retry, first = self.by_key.hit(key, limit, now)
        if ok and ok_ip:
            return True, 0, kind, False
        with self._lock:
            self.blocked_total["por_credencial" if (not ok and kind == "token") else "por_ip"] += 1
        return False, max(retry, retry_ip), (kind if not ok else "ip"), (first if not ok else first_ip)

    def snapshot(self) -> dict[str, Any]:
        c = self.cfg
        return {"ativo": c.enabled, "janela_s": c.window_s, "limite_por_credencial": c.token_max, "limite_por_ip_sem_token": c.ip_max, "teto_por_ip": c.ip_ceiling_max,
                "bloqueios_desde_o_inicio": dict(self.blocked_total), "chaves_ativas": self.by_key.size(), "escopo": "por instância, em memória (zera ao reiniciar)"}


RATE_LIMIT = RateLimitState()


class RateLimitMiddleware:
    """ASGI puro. Acima do limite: 429 genérico + Retry-After, log JSON estruturado (sem token, sem gravar no banco; só o 1º bloqueio por chave e janela, para o log não virar amplificador)."""

    def __init__(self, app: Any, state: RateLimitState | None = None) -> None:
        self.app = app
        self.state = state or RATE_LIMIT

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        st = self.state
        if scope["type"] != "http" or not st.cfg.enabled or scope.get("path") in RATE_LIMIT_EXEMPT_PATHS or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        req = Request(scope)
        ok, retry, kind, first = st.check(req.headers.get("authorization"), client_ip(req))
        if ok:
            await self.app(scope, receive, send)
            return
        if first:
            _log.warning("rate limit excedido", extra={"evt": "rate_limit.blocked", "chave": kind, "path": scope.get("path"), "retry_after_s": retry})
        await JSONResponse({"detail": RATE_LIMIT_MESSAGE}, status_code=429, headers={"Retry-After": str(retry)})(scope, receive, send)
