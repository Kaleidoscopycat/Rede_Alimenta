"""Teste de fumaça PÓS-DEPLOY, SOMENTE LEITURA (Fase 3 Parte 2 · Etapa B).

  python -m scripts.smoke_cloud --api https://SUA-API.onrender.com --frontend https://SEU-FRONT.onrender.com
  python -m scripts.smoke_cloud --api ... --frontend ... --acordar      # repete /health e /ready com espera crescente (~2 min) para acordar o plano gratuito

* Não grava dados (só GET) e não imprime tokens. Tokens opcionais vêm do AMBIENTE: SMOKE_DONOR_TOKEN, SMOKE_ORG_TOKEN (checagem de campos de IA)
  e SMOKE_ADMIN_TOKEN (não usado por padrão: chamadas ADMIN com token gravam auditoria).
* As URLs também podem vir de SMOKE_API_URL / SMOKE_FRONTEND_URL. Só HTTPS (exceto localhost).
* Saída: uma linha por verificação (OK / FALHA / PULADO) e código 0 só se nada falhou."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

PAUSED_MSG = "banco em nuvem pausado ou inacessível: retome o projeto no painel do Supabase (Resume project) e tente de novo"
FORBIDDEN_AI_KEYS = {"score", "scores", "ranking", "rank", "probability", "probabilidade", "model_version", "features", "ml_score", "rule_score", "final_score"}
TIMEOUT_S = 30


def _check_url(url: str) -> str:
    p = urlsplit(url)
    local = p.hostname in ("localhost", "127.0.0.1", "::1")
    if p.scheme != "https" and not (local and p.scheme == "http"):
        raise SystemExit(f"URL inválida (use https): {p.scheme}://{p.hostname or '?'}")
    if not p.hostname:
        raise SystemExit("URL sem host")
    return url.rstrip("/")


def http_get(url: str, token: str | None = None, timeout: int = TIMEOUT_S) -> tuple[int, str]:
    """GET simples; devolve (status, corpo). Erro de rede → (0, mensagem curta)."""
    headers = {"Accept": "application/json", "User-Agent": "smoke-cloud/1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")  # noqa: S310 (esquema validado em _check_url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310  # nosec B310
            return r.status, r.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read(200_000).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            return e.code, ""
    except Exception as e:  # noqa: BLE001
        return 0, type(e).__name__


def acordar(base: str, caminhos=("/health", "/ready"), max_s: float = 120.0, sleep=time.sleep, get=http_get) -> bool:
    """Repete GET até todos os caminhos devolverem 200 ou estourar `max_s`; espera cresce 2 s ×1.6 (máx 15 s)."""
    t0, delay = time.monotonic(), 2.0
    pendentes = list(caminhos)
    while True:
        pendentes = [c for c in pendentes if get(base + c)[0] != 200]
        if not pendentes:
            return True
        if time.monotonic() - t0 + delay > max_s:
            return False
        sleep(delay)
        delay = min(delay * 1.6, 15.0)


def find_forbidden(obj, path="") -> list[str]:
    """Procura chaves de IA proibidas (qualquer profundidade) numa resposta JSON."""
    achados: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in FORBIDDEN_AI_KEYS:
                achados.append(f"{path}/{k}")
            achados += find_forbidden(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:200]):
            achados += find_forbidden(v, f"{path}[{i}]")
    return achados


class Report:
    def __init__(self) -> None:
        self.falhas = 0
        self.linhas: list[tuple[str, str, str]] = []

    def add(self, estado: str, nome: str, detalhe: str = "") -> None:
        if estado == "FALHA":
            self.falhas += 1
        self.linhas.append((estado, nome, detalhe))
        print(f"[{estado}] {nome}" + (f" — {detalhe}" if detalhe else ""))


def run(api: str, frontend: str | None, do_wake: bool, env=os.environ, get=http_get, wake=acordar) -> Report:
    rep = Report()
    if do_wake:
        for nome, base in (("API", api), ("frontend", frontend)):
            if base:
                ok = wake(base) if nome == "API" else wake(base, ("/_stcore/health",))
                rep.add("OK" if ok else "FALHA", f"acordar {nome}", "" if ok else "não respondeu 200 em ~2 min")
    s, _ = get(api + "/health")
    rep.add("OK" if s == 200 else "FALHA", "API: GET /health", f"status {s}")
    if not frontend:
        rep.add("PULADO", "frontend", "URL não informada")
    s, corpo = get(api + "/ready")
    if s == 200:
        rep.add("OK", "API: GET /ready (banco acessível)")
    else:
        rep.add("FALHA", "API: GET /ready", PAUSED_MSG if s in (0, 503) else f"status {s}")
    if frontend:
        s, _ = get(frontend + "/_stcore/health")  # endpoint de saúde do Streamlit
        rep.add("OK" if s == 200 else "FALHA", "frontend: GET /_stcore/health", f"status {s}")
    for caminho in ("/docs", "/redoc", "/openapi.json"):
        s, _ = get(api + caminho)
        rep.add("OK" if s == 404 else "FALHA", f"API: {caminho} desabilitado em production", f"status {s} (esperado 404)")
    for caminho in ("/api/v1/admin/stats/overview", "/api/v1/admin/stats/security"):
        s, _ = get(api + caminho)
        rep.add("OK" if s in (401, 403) else "FALHA", f"API: {caminho} sem token", f"status {s} (esperado 401/403)")
    for perfil in ("DONOR", "ORG"):
        tok = env.get(f"SMOKE_{perfil}_TOKEN")
        if not tok:
            rep.add("PULADO", f"campos de IA ocultos para {perfil}", f"SMOKE_{perfil}_TOKEN não definido")
            continue
        rotas = ("/api/v1/donations", "/api/v1/matches", "/api/v1/me") if perfil == "DONOR" else ("/api/v1/matches", "/api/v1/me")
        ruim: list[str] = []
        for r in rotas:
            s, corpo = get(api + r, tok)
            if s != 200:
                continue
            try:
                ruim += find_forbidden(json.loads(corpo), r)
            except ValueError:
                pass
        rep.add("OK" if not ruim else "FALHA", f"campos de IA ocultos para {perfil}", ", ".join(ruim[:5]))
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default=os.environ.get("SMOKE_API_URL"))
    ap.add_argument("--frontend", default=os.environ.get("SMOKE_FRONTEND_URL"))
    ap.add_argument("--acordar", action="store_true")
    a = ap.parse_args(argv)
    if not a.api:
        print("informe --api (ou SMOKE_API_URL)")
        return 2
    rep = run(_check_url(a.api), _check_url(a.frontend) if a.frontend else None, a.acordar)
    print(f"\n{'FALHAS: ' + str(rep.falhas) if rep.falhas else 'Tudo certo.'}")
    return 1 if rep.falhas else 0


if __name__ == "__main__":
    sys.exit(main())
