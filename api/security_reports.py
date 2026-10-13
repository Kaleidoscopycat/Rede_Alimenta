"""Indicador "vulnerabilidades mitigadas" calculado a partir dos ARQUIVOS de relatório (Bandit, pip-audit, Trivy, gitleaks) em security/reports/.

Regras (AGENTS.md: não inventar números):
* só conta o que o arquivo presente comprova; arquivo ausente ou ilegível ⇒ "pendente", nunca estimativa;
* "mitigadas" = achados do relatório ANTES − achados do relatório DEPOIS, somente quando AMBOS os arquivos existem (piso zero);
* Fase 2: security/reports/antes e /depois. Estado atual da Fase 3 (ruff, Bandit, pip-audit): security/reports/fase3a.
* Trivy de imagem (CI): security/reports/ci/antes e /depois (JSON baixado do GitHub pelo responsável). Se faltar, o indicador mostra a pendência.
* Cada cálculo informa o arquivo de origem e o SHA-256 dele."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")


def reports_dir() -> Path:
    return Path(os.environ.get("SECURITY_REPORTS_DIR", str(ROOT / "security" / "reports")))


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def _json(p: Path) -> Any | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(reports_dir()).as_posix())
    except ValueError:
        return p.name


def summarize_bandit(p: Path) -> dict[str, Any] | None:
    d = _json(p)
    if not isinstance(d, dict) or "results" not in d:
        return None
    sev = {k: 0 for k in ("HIGH", "MEDIUM", "LOW")}
    for r in d["results"]:
        sev[str(r.get("issue_severity", "LOW")).upper()] = sev.get(str(r.get("issue_severity", "LOW")).upper(), 0) + 1
    mt = (d.get("metrics") or {}).get("_totals", {})
    return {"arquivo": _rel(p), "sha256_16": _sha(p), "achados": len(d["results"]), "por_severidade": sev, "linhas_analisadas": int(mt.get("loc", 0)),
            "supressoes_nosec": int(mt.get("skipped_tests", 0)), "gerado_em": d.get("generated_at")}


def summarize_pip_audit(p: Path) -> dict[str, Any] | None:
    d = _json(p)
    if not isinstance(d, dict) or "dependencies" not in d:
        return None
    deps = d["dependencies"]
    n_vuln = sum(len(x.get("vulns", [])) for x in deps)
    return {"arquivo": _rel(p), "sha256_16": _sha(p), "dependencias": len(deps), "achados": n_vuln}


def summarize_trivy(p: Path) -> dict[str, Any] | None:
    d = _json(p)
    if not isinstance(d, dict) or "Results" not in d and "SchemaVersion" not in d:
        return None
    sev = {k: 0 for k in SEVERITIES}
    fixable_hc = n_secret = n_misconf = 0
    for res in d.get("Results") or []:
        for v in res.get("Vulnerabilities") or []:
            s = str(v.get("Severity", "UNKNOWN")).upper()
            sev[s if s in sev else "UNKNOWN"] += 1
            if s in ("HIGH", "CRITICAL") and v.get("FixedVersion"):
                fixable_hc += 1
        n_secret += len(res.get("Secrets") or [])
        n_misconf += len([x for x in (res.get("Misconfigurations") or []) if str(x.get("Status", "FAIL")).upper() == "FAIL"])
    hc = sev["HIGH"] + sev["CRITICAL"]
    return {"arquivo": _rel(p), "sha256_16": _sha(p), "alvo": d.get("ArtifactName"), "vulnerabilidades": sum(sev.values()), "por_severidade": sev, "high_critical": hc,
            "high_critical_corrigiveis": fixable_hc, "segredos": n_secret, "misconfiguracoes": n_misconf, "achados": hc + n_secret + n_misconf}


def summarize_gitleaks(p: Path) -> dict[str, Any] | None:
    d = _json(p)
    if not isinstance(d, list):
        return None
    return {"arquivo": _rel(p), "sha256_16": _sha(p), "achados": len(d)}


def _pair(tool: str, antes: dict | None, depois: dict | None, unidade: str, key: str = "achados") -> dict[str, Any]:
    comprovado = antes is not None and depois is not None
    out: dict[str, Any] = {"ferramenta": tool, "unidade": unidade, "antes": antes, "depois": depois, "comprovado": comprovado, "mitigadas": None, "situacao": ""}
    if comprovado:
        out["mitigadas"] = max(0, int(antes[key]) - int(depois[key]))
        out["situacao"] = f"{antes[key]} → {depois[key]} ({unidade})"
    else:
        faltam = [n for n, v in (("antes", antes), ("depois", depois)) if v is None]
        out["situacao"] = "pendente: relatório " + " e ".join(faltam) + " ausente — nenhum número é estimado"
    return out


def _ci_images(dirpath: Path) -> list[dict[str, Any]]:
    out = []
    if dirpath.is_dir():
        for p in sorted(dirpath.glob("*.json")):
            s = summarize_trivy(p)
            if s is not None:
                out.append(s)
    return out


def compute() -> dict[str, Any]:
    root = reports_dir()
    f2 = {"bandit": _pair("Bandit (SAST)", summarize_bandit(root / "antes" / "bandit.json"), summarize_bandit(root / "depois" / "bandit.json"), "achados"),
          "pip_audit": _pair("pip-audit (dependências)", summarize_pip_audit(root / "antes" / "pip-audit.json"), summarize_pip_audit(root / "depois" / "pip-audit.json"), "vulnerabilidades"),
          "trivy_fs": _pair("Trivy fs (segredos + configuração)", summarize_trivy(root / "antes" / "trivy-fs-secret-misconfig.json"),
                            summarize_trivy(root / "depois" / "trivy-fs-secret-misconfig.json"), "achados"),
          "gitleaks": _pair("gitleaks (histórico Git)", summarize_gitleaks(root / "antes" / "gitleaks-historico.json"), summarize_gitleaks(root / "depois" / "gitleaks-historico.json"), "segredos")}
    resumo = _json(root / "resumo_antes_depois.json") or {}
    det = (resumo.get("mitigadas") or {}) if isinstance(resumo, dict) else {}
    bandit_detail = {"corrigidas_no_codigo": det.get("corrigidas_no_codigo"), "suprimidas_com_justificativa": det.get("suprimidas_com_justificativa"), "fonte": "resumo_antes_depois.json e SUPRESSOES.md"} if det else None
    ci_antes, ci_depois = _ci_images(root / "ci" / "antes"), _ci_images(root / "ci" / "depois")
    if ci_antes and ci_depois:
        a, d = sum(x["high_critical"] for x in ci_antes), sum(x["high_critical"] for x in ci_depois)
        ci = {"comprovado": True, "antes": ci_antes, "depois": ci_depois, "high_critical_antes": a, "high_critical_depois": d, "mitigadas": max(0, a - d),
              "situacao": f"HIGH/CRITICAL nas imagens do CI: {a} → {d}"}
    else:
        ci = {"comprovado": False, "antes": ci_antes, "depois": ci_depois, "high_critical_antes": None, "high_critical_depois": None, "mitigadas": None,
              "situacao": ("pendente: relatórios JSON do Trivy de imagem do CI (antes/depois) não encontrados em security/reports/ci/antes e /depois — "
                           "nenhum número é estimado. Há registro textual do caso em docs/FASE2_P2_RELATORIO_FINAL.md e nos logs do CI, mas ele não é contabilizado sem o arquivo.")}
    atual = {"bandit": summarize_bandit(root / "fase3a" / "bandit.json"), "pip_audit": summarize_pip_audit(root / "fase3a" / "pip-audit.json"), "trivy_fs": summarize_trivy(root / "fase3a" / "trivy-fs.json")}
    ruff_p = root / "fase3a" / "ruff.txt"
    try:
        atual["ruff"] = {"arquivo": _rel(ruff_p), "resultado": ruff_p.read_text(encoding="utf-8").strip()[:200]}
    except OSError:
        atual["ruff"] = None
    comprovadas = [x for x in list(f2.values()) + [ci] if x["comprovado"]]
    total = sum(int(x["mitigadas"]) for x in comprovadas)
    return {"fase2": f2, "bandit_detalhe": bandit_detail, "trivy_imagem_ci": ci, "estado_atual_fase3a": atual, "total_mitigadas_comprovadas": total,
            "ferramentas_comprovadas": [x.get("ferramenta", "Trivy imagem (CI)") for x in comprovadas],
            "pendencias": [x["situacao"] for x in list(f2.values()) + [ci] if not x["comprovado"]],
            "diretorio": "security/reports", "data_origin": "PUBLIC",
            "nota": "Escopo: código do projeto, dependências e imagens. Não mede a segurança da aplicação em produção. A contagem 'mitigadas' inclui achados corrigidos no código e achados suprimidos com justificativa (ver bandit_detalhe)."}
