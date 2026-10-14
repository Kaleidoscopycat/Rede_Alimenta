"""Enriquecimento do contrato OpenAPI (Fase 4 · Etapa A · A6).

Como `/docs`, `/redoc` e `/openapi.json` ficam DESLIGADOS em produção (`APP_ENV=production`), o contrato público da API é versionado em `docs/openapi.json`
(gerado por `python -m scripts.export_openapi` e conferido por `tests/test_p4a_openapi.py`).

Este módulo NÃO altera nenhuma rota, regra de autorização ou resposta real: apenas completa a DESCRIÇÃO do contrato gerado pelo FastAPI com
(1) o modelo de erro `ErrorOut` e as respostas de erro padronizadas, (2) descrição de /health e /ready, (3) descrição das tags e (4) exemplos GENÉRICOS
(sem dados reais: nenhum nome, CNPJ, endereço ou pessoa).
"""
from __future__ import annotations

from typing import Any

ERROR_SCHEMA = "ErrorOut"

# (código, descrição) — só códigos que a API realmente devolve (ver api/auth.py, api/core e os routers)
_ERROS_COMUNS = {
    "401": "Token ausente, inválido, expirado ou inativo. A mensagem é genérica (`credenciais inválidas`); o motivo só vai para a auditoria.",
    "403": "Quando a rota restringe perfis ou posse: perfil sem permissão para o recurso, ou recurso de outro usuário (a negativa é auditada).",
    "429": "Limite excedido: (a) muitas tentativas de autenticação inválidas do mesmo IP ou (b) muitas requisições na janela (limite global por token — ou por IP quando não há token válido no formato —, em memória, por instância; `/health` e `/ready` são isentos). Cabeçalho `Retry-After` em segundos.",
    "500": "Erro interno genérico (`erro interno`) com `request_id`; o detalhe fica só no log do servidor.",
}
_ERRO_404 = "Recurso inexistente (quando a rota recebe identificador)."
_ERRO_409 = "Quando aplicável à operação: o estado atual do recurso não permite a transição (ex.: doação já finalizada, organização ainda não cadastrada)."

TAGS = [
    {"name": "infra", "description": "Verificações de saúde para a plataforma de hospedagem. Públicas (sem token)."},
    {"name": "organizações", "description": "ONGs e bancos de alimentos de fonte PÚBLICA (pessoas jurídicas, por pseudônimo). Não são clientes da plataforma até o cadastro."},
    {"name": "dados públicos", "description": "Fontes públicas reais, versões e situação de licença."},
    {"name": "doadores", "description": "Doadores (pessoas jurídicas). Os de demonstração são SIMULADOS."},
    {"name": "doações", "description": "Doação de lote único (fluxo antigo; `/donations/parse` é descontinuado para o perfil DONOR)."},
    {"name": "rascunho e itens", "description": "Doação item a item: rascunho, itens manuais ou sugeridos pelo texto (a confirmar) e finalização."},
    {"name": "matches", "description": "Recomendação doador → ONG. Cada perfil recebe uma visão diferente da resposta (scores e ranking só para ADMIN)."},
    {"name": "modelo", "description": "Somente ADMIN. Predição direta e informações do modelo (treinado em dados SIMULADOS)."},
    {"name": "conta e administração", "description": "Identidade do token e administração de contas (ADMIN)."},
    {"name": "dashboard (ADMIN)", "description": "Indicadores agregados com selo de origem (PÚBLICO / SIMULADO / MEDIDO). Somente ADMIN, acesso auditado."},
    {"name": "routes", "description": "Planejamento de rotas de coleta (ORG e ADMIN). Distâncias e tempos são ESTIMATIVAS, não rota viária."},
]

INFRA = {
    ("get", "/health"): ("Verifica se o processo da API está de pé. Não consulta o banco.", "Sem autenticação."),
    ("get", "/ready"): ("Verifica se a API está pronta: modelo e parser carregados e banco acessível. Usado como health check pela plataforma de hospedagem.", "Sem autenticação."),
}

# Exemplos GENÉRICOS (nada real). Chave: nome do schema em components.schemas.
EXEMPLOS = {
    ERROR_SCHEMA: [{"detail": "mensagem de erro genérica", "request_id": "0123456789abcdef0123456789abcdef"}],
    "DraftIn": [{"contem_alergenico": False, "janela_retirada_inicio_h": 8, "janela_retirada_fim_h": 17, "tempo_carga_min": 30}],
    "ItemIn": [{"produto": "alimento de exemplo", "categoria": "GRAOS_CEREAIS", "quantity": 10, "unit": "pacote", "unit_weight": 1, "unit_weight_unit": "kg",
                "validade_data": "2030-01-31", "exige_refrigeracao": False}],
    "RespondIn": [{"accept": True, "note": "texto opcional"}],
}

DESCRICAO = (
    "Conecta DOADOR → ONG. **Modelos treinados em dados SIMULADOS; atributos declarados das ONGs são SIMULADOS; métricas não representam desempenho real.** "
    "Autenticação: `Authorization: Bearer <token>` (perfis DONOR, ORG, ADMIN); token estático, com expiração opcional e revogação manual. "
    "TLS é terminado pela plataforma de hospedagem; há limite de tentativas de autenticação inválidas por IP e limite global de requisições por token (ou por IP, sem token), ambos em memória e por instância (não distribuídos). "
    "Em produção esta documentação interativa fica desligada: o contrato versionado está em `docs/openapi.json`. "
    "Cada perfil recebe uma visão diferente das respostas (ver `docs/ROLE_VISIBILITY.md`)."
)


def _error_ref() -> dict[str, Any]:
    return {"$ref": f"#/components/schemas/{ERROR_SCHEMA}"}


def _resposta(desc: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    r: dict[str, Any] = {"description": desc, "content": {"application/json": {"schema": _error_ref()}}}
    if extra:
        r["headers"] = extra
    return r


def enriquecer(schema: dict[str, Any]) -> dict[str, Any]:
    """Completa (in place) o dicionário OpenAPI gerado pelo FastAPI. Idempotente."""
    comps = schema.setdefault("components", {}).setdefault("schemas", {})
    comps[ERROR_SCHEMA] = {
        "type": "object", "title": ERROR_SCHEMA,
        "description": "Corpo de erro genérico. Nunca contém token, caminho de arquivo, traceback nem detalhe interno.",
        "properties": {"detail": {"type": "string", "description": "Mensagem curta e genérica (ou, em 422, a lista de erros de validação do FastAPI)."},
                       "request_id": {"type": "string", "description": "Identificador da requisição (também no cabeçalho `X-Request-ID`), presente em erros 500."}},
        "required": ["detail"],
    }
    for nome, ex in EXEMPLOS.items():
        if nome in comps:
            comps[nome]["examples"] = ex
    for path, ops in schema.get("paths", {}).items():
        for metodo, op in ops.items():
            if (metodo, path) in INFRA:
                resumo, auth = INFRA[(metodo, path)]
                op["summary"] = {"/health": "Saúde do processo", "/ready": "Prontidão (modelo e banco)"}[path]
                op["description"] = f"{resumo} {auth}"
                if path == "/ready":
                    op["responses"]["503"] = {"description": "Modelo ou banco indisponível.", "content": {"application/json": {"schema": {"type": "object"}}}}
                continue
            if not path.startswith("/api/v1"):
                continue
            resp = op.setdefault("responses", {})
            for cod, desc in _ERROS_COMUNS.items():
                extra = {"Retry-After": {"description": "Segundos até poder tentar de novo.", "schema": {"type": "integer"}}} if cod == "429" else None
                resp[cod] = _resposta(desc, extra)
            if "{" in path:
                resp["404"] = _resposta(_ERRO_404)
            if metodo in ("post", "patch", "put", "delete"):
                resp["409"] = _resposta(_ERRO_409)
    schema["tags"] = TAGS
    return schema


def instalar(app: Any) -> None:
    """Substitui `app.openapi` por uma versão que aplica `enriquecer` uma única vez (o resultado fica em cache, como o do FastAPI)."""
    original = app.openapi

    def openapi() -> dict[str, Any]:
        if getattr(app, "_openapi_enriquecido", False) and app.openapi_schema:
            return app.openapi_schema
        schema = original()
        enriquecer(schema)
        app.openapi_schema = schema
        app._openapi_enriquecido = True
        return schema

    app.openapi = openapi
