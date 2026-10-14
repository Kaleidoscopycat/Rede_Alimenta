"""Fase 4 · Etapa B — rate limit GLOBAL por requisição (core/hardening.py). Parte sem banco (contador, middleware isolado) e parte com o app real (banco de teste)."""
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.hardening import RATE_LIMIT, FixedWindowCounter, RateLimitConfig, RateLimitMiddleware, RateLimitState

TOKEN_A = "rai_" + "A" * 43
TOKEN_B = "rai_" + "B" * 43


def _app(**cfg) -> tuple[TestClient, RateLimitState]:
    st = RateLimitState(RateLimitConfig(**cfg))
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, state=st)

    @app.get("/x")
    def x():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        return {"status": "ready"}
    return TestClient(app), st


# --------------------------------------------------------------------------------------- contador
def test_contador_abaixo_passa_acima_bloqueia_e_a_janela_vira():
    c = FixedWindowCounter(window_s=60)
    assert all(c.hit("k", 3, now=t)[0] for t in (0, 1, 2))
    ok, retry, primeiro = c.hit("k", 3, now=3)
    assert (ok, primeiro) == (False, True) and 1 <= retry <= 60
    assert c.hit("k", 3, now=4)[2] is False  # só o 1º bloqueio da janela é "primeiro" (log não vira amplificador)
    assert c.hit("k", 3, now=61)[0] is True  # janela nova


def test_chaves_diferentes_nao_se_afetam():
    c = FixedWindowCounter(window_s=60)
    for _ in range(5):
        c.hit("a", 2, now=1)
    assert c.hit("a", 2, now=2)[0] is False and c.hit("b", 2, now=2)[0] is True


def test_limpeza_de_chaves_vencidas_e_teto_de_memoria():
    c = FixedWindowCounter(window_s=10, max_keys=50)
    for i in range(40):
        c.hit(f"k{i}", 5, now=0)
    assert c.size() == 40
    c.hit("novo", 5, now=100)  # varredura preguiçosa remove as janelas vencidas
    assert c.size() == 1
    for i in range(500):  # ataque com muitas chaves: nunca passa do teto
        c.hit(f"x{i}", 5, now=100)
    assert c.size() <= 50


# --------------------------------------------------------------------------------------- estado: chave por token ou IP
def test_chave_e_o_hash_do_token_e_o_token_nao_e_guardado():
    st = RateLimitState(RateLimitConfig(token_max=2, ip_max=1000, ip_ceiling_max=1000))
    h = f"Bearer {TOKEN_A}"
    assert [st.check(h, "9.9.9.9", now=1)[0] for _ in range(3)] == [True, True, False]
    assert st.check(f"Bearer {TOKEN_B}", "9.9.9.9", now=1)[0] is True  # outro token, MESMO IP (frontend compartilhado): não é afetado
    assert not any(TOKEN_A in k or TOKEN_B in k for k in st.by_key._d) and all(k.startswith(("t:", "i:")) for k in st.by_key._d)


def test_sem_token_ou_formato_invalido_usa_o_ip():
    st = RateLimitState(RateLimitConfig(token_max=1000, ip_max=2, ip_ceiling_max=1000))
    for auth in (None, "", "Bearer curto", "Basic abc", "Bearer rai_$$$$$$$$$$$$$$$$$$$$$$$$"):
        st.by_key.clear()
        assert [st.check(auth, "1.1.1.1", now=1)[0] for _ in range(3)] == [True, True, False], auth
    assert st.check(None, "2.2.2.2", now=1)[0] is True  # IP diferente


def test_teto_por_ip_vale_mesmo_girando_tokens():
    st = RateLimitState(RateLimitConfig(token_max=1000, ip_max=1000, ip_ceiling_max=5))
    r = [st.check(f"Bearer rai_{i:043d}", "3.3.3.3", now=1)[0] for i in range(7)]
    assert r == [True] * 5 + [False] * 2


# --------------------------------------------------------------------------------------- middleware isolado
def test_middleware_429_generico_com_retry_after_e_sem_token_no_corpo():
    c, st = _app(token_max=3, ip_max=100, ip_ceiling_max=100)
    h = {"Authorization": f"Bearer {TOKEN_A}"}
    assert [c.get("/x", headers=h).status_code for _ in range(3)] == [200, 200, 200]
    r = c.get("/x", headers=h)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert r.json() == {"detail": "muitas requisições; aguarde e tente novamente"} and TOKEN_A not in r.text and TOKEN_A not in str(r.headers)
    assert c.get("/x", headers={"Authorization": f"Bearer {TOKEN_B}"}).status_code == 200
    assert st.snapshot()["bloqueios_desde_o_inicio"]["por_credencial"] == 1


def test_health_e_ready_sao_isentos():
    c, _ = _app(token_max=1, ip_max=1, ip_ceiling_max=1)
    assert {c.get(p).status_code for p in ("/health", "/ready") for _ in range(20)} == {200}
    assert c.get("/x").status_code == 200 and c.get("/x").status_code == 429


def test_desligado_por_configuracao():
    c, _ = _app(enabled=False, token_max=1, ip_max=1, ip_ceiling_max=1)
    assert {c.get("/x").status_code for _ in range(10)} == {200}


def test_config_por_ambiente(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("RATE_LIMIT_TOKEN_MAX", "7")
    cfg = RateLimitConfig.from_env()
    assert cfg.enabled is False and cfg.token_max == 7 and cfg.ip_max == 240 and cfg.ip_ceiling_max == 6000 and cfg.window_s == 60
    monkeypatch.setenv("RATE_LIMIT_TOKEN_MAX", "abc")
    with pytest.raises(RuntimeError):
        RateLimitConfig.from_env()
    monkeypatch.setenv("RATE_LIMIT_TOKEN_MAX", "0")
    with pytest.raises(RuntimeError):
        RateLimitConfig.from_env()


def test_log_estruturado_sem_token_e_so_no_primeiro_bloqueio(caplog):
    c, _ = _app(token_max=1, ip_max=100, ip_ceiling_max=100)
    h = {"Authorization": f"Bearer {TOKEN_A}"}
    with caplog.at_level(logging.WARNING, logger="api.ratelimit"):
        for _ in range(6):
            c.get("/x?segredo=1", headers=h)
    regs = [r for r in caplog.records if r.name == "api.ratelimit"]
    assert len(regs) == 1 and regs[0].evt == "rate_limit.blocked" and regs[0].chave == "token"
    tudo = " ".join(f"{r.getMessage()} {r.__dict__}" for r in regs)
    assert TOKEN_A not in tudo and "segredo" not in tudo and "testclient" not in tudo  # sem token, sem query string, sem IP


def test_padroes_sao_generosos_para_a_demonstracao():
    cfg = RateLimitConfig()
    sessoes_com_36_chamadas_por_min = cfg.token_max // 36  # tela do doador/ONG: ≈12 atualizações/min × até 3 chamadas (estimativa de projeto)
    assert cfg.enabled and cfg.window_s == 60 and sessoes_com_36_chamadas_por_min >= 30 and cfg.ip_ceiling_max > cfg.token_max > cfg.ip_max


# --------------------------------------------------------------------------------------- app real (banco de teste)
@pytest.fixture()
def limite_pequeno():
    antigo = RATE_LIMIT.cfg
    RATE_LIMIT.by_key.clear(), RATE_LIMIT.by_ip.clear()
    RATE_LIMIT.cfg = RateLimitConfig(token_max=6, ip_max=6, ip_ceiling_max=1000)
    yield RATE_LIMIT
    RATE_LIMIT.cfg = antigo
    RATE_LIMIT.by_key.clear(), RATE_LIMIT.by_ip.clear()
    RATE_LIMIT.blocked_total.update(por_credencial=0, por_ip=0)


def test_app_real_limita_por_credencial_sem_derrubar_os_outros(client, world, limite_pequeno):
    r = [client.get("/api/v1/me", headers=world["admin"]).status_code for _ in range(8)]
    assert r[:6] == [200] * 6 and r[6:] == [429, 429]
    assert client.get("/api/v1/me", headers=world["donor_a"]).status_code == 200  # outro token, mesmo IP do teste
    assert client.get("/health").status_code == 200 and client.get("/ready").status_code == 200


def test_app_real_expoe_contador_ao_admin(client, world, limite_pequeno):
    for _ in range(8):
        client.get("/api/v1/me", headers=world["donor_b"])
    limite_pequeno.by_key.clear()  # libera o ADMIN para consultar
    s = client.get("/api/v1/admin/stats/security", headers=world["admin"]).json()["sistema"]["rate_limit"]
    assert s["ativo"] is True and s["limite_por_credencial"] == 6 and s["bloqueios_desde_o_inicio"]["por_credencial"] >= 2 and s["chaves_ativas"] >= 1


def test_padroes_nao_quebram_o_fluxo_normal(client, world):
    assert RATE_LIMIT.cfg.token_max == 1200
    assert {client.get("/api/v1/me", headers=world["admin"]).status_code for _ in range(30)} == {200}
