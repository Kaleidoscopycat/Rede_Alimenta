"""Download/extract automatizado das fontes, com verificação de integridade do RAW.

Política (AGENTS.md): o RAW nunca é sobrescrito em silêncio. Para cada fonte:
  1. se o arquivo RAW existe, compara o sha256 com a linha de base registrada na Fase 0;
  2. com --refresh tenta baixar para data/incoming/ e compara; divergência é REGISTRADA
     (não substitui o RAW); falha de rede é REGISTRADA (não é ocultada).
Somente URLs documentadas em docs/data/ são usadas. Fontes sem URL de arquivo registrada
têm `url=None` e `status` explica por quê (nada é inventado).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import requests

from .common import BASELINE_CHECKSUMS, RAW, ROOT, get_logger, now_utc, register, sha256_file

log = get_logger("download")


@dataclass
class Source:
    source_id: str
    source_name: str
    source_dataset: str
    local_path: str
    url: str | None
    landing_page: str
    license_status: str
    source_updated_at: str
    notes: str = ""
    extra: dict = field(default_factory=dict)


SOURCES = [
    Source("ibge_municipios", "IBGE", "Municípios (API Localidades)", "data/raw/ibge/ibge_municipios.json",
           "https://servicodados.ibge.gov.br/api/v1/localidades/municipios",
           "https://servicodados.ibge.gov.br/api/v1/localidades/municipios",
           "dado aberto; licença explícita NÃO localizada (APPROVED* p/ pesquisa)", "não verificável"),
    Source("ibge_populacao", "IBGE/SIDRA", "População estimada 2026 (agregado 6579)", "data/raw/ibge/ibge_populacao_municipios_2026.json",
           None, "https://servicodados.ibge.gov.br/api/v3/agregados/6579",
           "dado aberto; licença explícita NÃO localizada", "2026",
           "URL exata (variável/período/localidades) usada na Fase 0 não foi registrada; só a base do agregado consta em DATA_LINEAGE."),
    Source("ibge_coords", "kelvins/municipios-brasileiros (terceiros)", "Coordenadas de municípios", "data/raw/ibge_coords/kelvins_municipios.csv",
           "https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv",
           "https://github.com/kelvins/municipios-brasileiros", "MIT (repositório); origem primária NÃO confirmada (PROXY)", "commit 2025-12-10"),
    Source("ipea_osc_area", "IPEA", "Mapa das OSCs: área/subárea", "data/raw/ipea_osc/area_subarea.csv",
           None, "https://dados.gov.br/dados/conjuntos-dados/mapaosc",
           "Other (Attribution); uso comercial NÃO confirmado (NEEDS_REVIEW)", "não verificável",
           "URL direta do CSV não registrada na Fase 0; dados.gov.br retorna 401 a leitor automático e está bloqueado neste ambiente."),
    Source("rbba_resumo", "MDS/Alimenta Cidades", "RBBA resumo 2025", "data/raw/rbba/rbba_resumo.json",
           "https://alimentacidades.digital/rbba/api/resumo",
           "https://www.gov.br/mds/pt-br/acoes-e-programas/acesso-a-alimentos-e-a-agua/rede-brasileira-de-bancos-de-alimentos",
           "NÃO declarada (NEEDS_REVIEW); endpoint não documentado", "2025"),
] + [
    Source(f"paa_{k}", "MDS/SAGI", t, f"data/raw/paa_mds/{f}", None,
           "https://aplicacoes.mds.gov.br/sagi/servicos/misocial", "CC-BY (metadado dados.gov.br, Fase 0)", "2026-06",
           "URL/consulta exata não registrada na Fase 0; domínio bloqueado neste ambiente.")
    for k, t, f in [("compra_doacao", "PAA Compra c/ Doação Simultânea", "paa_execucao_compra_doacao_simultanea.csv"),
                    ("leite", "PAA Incentivo ao Leite", "paa_execucao_leite.csv"),
                    ("municipios", "PAA Municípios Aderidos", "paa_municipios_aderidos_2026.csv")]
]


def _baseline() -> dict:
    return json.loads(BASELINE_CHECKSUMS.read_text(encoding="utf-8")) if BASELINE_CHECKSUMS.exists() else {}


def verify_and_fetch(refresh: bool = False, timeout: int = 60) -> list[dict]:
    base = _baseline()
    results = []
    for s in SOURCES:
        p = ROOT / s.local_path
        rec: dict = {"source_url": s.url or s.landing_page, "source_name": s.source_name,
                     "source_dataset": s.source_dataset, "source_updated_at": s.source_updated_at,
                     "license_status": s.license_status, "raw_path": s.local_path}
        if p.exists():
            digest = sha256_file(p)
            ref = base.get(s.local_path, {}).get("sha256")
            rec.update(raw_sha256=digest, raw_bytes=p.stat().st_size,
                       raw_integrity="IGUAL_A_FASE0" if ref == digest else ("SEM_LINHA_DE_BASE" if ref is None else "DIVERGENTE_DA_FASE0"))
            rec["ingested_at"] = rec.get("ingested_at") or now_utc()
        else:
            rec["raw_integrity"] = "AUSENTE"
        rec["download_attempt"] = "NAO_SOLICITADO"
        if refresh:
            if s.url is None:
                rec["download_attempt"] = "SEM_URL_REGISTRADA"
                rec["download_note"] = s.notes
            else:
                try:
                    r = requests.get(s.url, timeout=timeout, headers={"User-Agent": "rede-alimenta-ia-pipeline/1.0"})
                    r.raise_for_status()
                    inc = RAW.parent / "incoming" / p.name
                    inc.parent.mkdir(parents=True, exist_ok=True)
                    inc.write_bytes(r.content)
                    new = sha256_file(inc)
                    rec.update(download_attempt="OK", incoming_sha256=new, incoming_bytes=len(r.content),
                               incoming_equals_raw=bool(p.exists() and new == rec.get("raw_sha256")),
                               downloaded_at=now_utc())
                    if not rec["incoming_equals_raw"]:
                        rec["download_note"] = "Conteúdo novo diferente do RAW atual: RAW NÃO foi substituído (revisão manual)."
                except Exception as e:  # registrar, nunca ocultar
                    rec.update(download_attempt="FALHA", download_error=f"{type(e).__name__}: {str(e)[:200]}")
                    rec["download_note"] = s.notes
        log.info("%s: %s", s.source_id, {k: rec.get(k) for k in ("raw_integrity", "download_attempt")})
        register(s.source_id, **rec)
        results.append(rec)
    return results
