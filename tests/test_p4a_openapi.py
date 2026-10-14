"""Fase 4 · Etapa A · A6 — contrato OpenAPI versionado (`docs/openapi.json`).

Em produção `/openapi.json` fica desligado (404); o contrato público é o arquivo versionado. Estes testes garantem que:
* o arquivo confere com o gerado pela aplicação (sem servidor, sem banco);
* nenhum campo de IA (scores, ranking, saída do parser...) aparece nos modelos de resposta de DONOR e ORG (varredura dos schemas, seguindo `$ref`);
* as respostas de erro padronizadas e as descrições existem, e o contrato não contém token nem exemplo com dado real.
Não precisam de banco (não usam o fixture `client`)."""
import json
import re
from pathlib import Path

from scripts.export_openapi import DESTINO, gerar
from tests.test_p3a_visibilidade_perfil import PROIBIDAS
from tests.test_p3b_campos_ia_proibidos import CONF, SAIDA_PARSER

ROOT = Path(__file__).resolve().parents[1]
RAIZES_DONOR_ORG = ("DonorDonationView", "DonorMatchView", "OrgDonationView", "OrgMatchView", "OrgCandidacy", "OrgLinha")


def _props(schemas: dict, nome: str, vistos: set[str]) -> set[str]:
    """Nomes de propriedades do schema e de todos os schemas alcançáveis por `$ref`."""
    if nome in vistos or nome not in schemas:
        return set()
    vistos.add(nome)
    out: set[str] = set()

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("properties"), dict):
                out.update(o["properties"])
            ref = o.get("$ref")
            if isinstance(ref, str):
                out.update(_props(schemas, ref.rsplit("/", 1)[-1], vistos))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(schemas[nome])
    return out


def test_openapi_versionado_confere_com_a_aplicacao():
    assert DESTINO.exists(), "docs/openapi.json ausente: rode `python -m scripts.export_openapi`"
    assert json.loads(DESTINO.read_text(encoding="utf-8")) == gerar(), "docs/openapi.json desatualizado: rode `python -m scripts.export_openapi`"


def test_modelos_de_donor_e_org_nao_declaram_campos_de_ia():
    schemas = json.loads(DESTINO.read_text(encoding="utf-8"))["components"]["schemas"]
    ausentes = [r for r in RAIZES_DONOR_ORG if r not in schemas]
    assert not ausentes, f"modelos esperados ausentes do contrato: {ausentes}"
    for raiz in RAIZES_DONOR_ORG:
        nomes = _props(schemas, raiz, set())
        assert nomes, raiz
        proibidos = {n for n in nomes if n in SAIDA_PARSER or n in PROIBIDAS or CONF.search(n)}
        assert not proibidos, f"{raiz} declara campo(s) de IA: {sorted(proibidos)}"
    # contraprova: o modelo do ADMIN continua declarando o que os outros não podem ter
    assert {"fields", "parser_version"} <= _props(schemas, "AdminDonationView", set())


def test_respostas_de_erro_padronizadas_e_descricoes():
    c = json.loads(DESTINO.read_text(encoding="utf-8"))
    assert "ErrorOut" in c["components"]["schemas"]
    for path, ops in c["paths"].items():
        for metodo, op in ops.items():
            assert not re.fullmatch(r"(Get|Post|Patch|Put|Delete) [A-Z][\w ]*", op.get("summary", "")), f"resumo automático sem descrição: {metodo.upper()} {path}"
            if path.startswith("/api/v1"):
                for cod in ("401", "403", "429", "500"):
                    assert op["responses"][cod]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorOut"), (metodo, path, cod)
                if "{" in path:
                    assert "404" in op["responses"], (metodo, path)
    for p in ("/health", "/ready"):
        assert c["paths"][p]["get"].get("description")
        assert not c["paths"][p]["get"].get("security")
    assert "Sem TLS/rate limit nesta fase" not in c["info"]["description"]


def test_contrato_sem_token_nem_dado_real():
    txt = DESTINO.read_text(encoding="utf-8")
    assert not re.search(r"rai_[A-Za-z0-9_\-]{20,}", txt), "token no contrato"
    assert not re.search(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b", txt), "padrão de CNPJ no contrato"
    assert not re.search(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", txt), "padrão de CPF no contrato"
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", txt), "e-mail no contrato"
