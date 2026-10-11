"""CONJUNTO PROVISÓRIO de descrições escritas por IA (NÃO é MANUALLY_LABELED).

O AGENTS.md exige um conjunto escrito e rotulado À MÃO pela equipe (data_origin = MANUALLY_LABELED). Esse conjunto ainda NÃO existe
(depende da equipe: tamanho, anotadores, dupla rotulagem; ver DATA_SIMULATION_SPEC §7). Para ter ao menos uma checagem fora dos
modelos de frase do gerador, este arquivo contém ~80 textos redigidos por IA de forma independente dos modelos do gerador, com rótulos
atribuídos pela mesma IA. Por isso:
  - data_origin = SIMULATED e authoring = IA_RASCUNHO_PROVISORIO_REVISAO_PENDENTE (nunca MANUALLY_LABELED);
  - NÃO substitui o conjunto da equipe; é pequeno (IC largo) e pode conter erros de rótulo;
  - NUNCA entra em treino, validação ou escolha de limiar.
Regra de rótulo adotada: exige_refrigeracao = True se a categoria é refrigerada (cárneos, laticínios/ovos, refeições prontas) ou se o texto menciona
refrigeração/congelamento/câmara fria; caso contrário False. Categoria INDEFINIDO = o texto não permite identificar (deve ir para confirmação humana).
validity_source = INFERIDA_PELA_CATEGORIA só quando a categoria é identificável e de vida curta (padaria, refeições prontas, folhosas).
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import yaml

from simulation.params import TAXONOMY_FILE

REF = dt.date(2026, 10, 5)
D = dt.date
# (texto, categoria, categoria2, produto, quantidade, unidade, vencimento|None, source, flags)
ITEMS = [
    ("Alface crespa e americana, 20 caixas, chegaram hoje e vencem em 2 dias", "HORT_FOLHOSAS", None, "alface", 20, "caixa", D(2026, 10, 7), "INFORMADA", ""),
    ("Couve manteiga fresquinha, 80 maços, só dura até amanhã.", "HORT_FOLHOSAS", None, "couve", 80, "unidade", D(2026, 10, 6), "INFORMADA", ""),
    ("Tenho 15 kg de espinafre e não tenho como armazenar", "HORT_FOLHOSAS", None, "espinafre", 15, "kg", None, "INFERIDA_PELA_CATEGORIA", ""),
    ("verduras variadas das sobras de hoje, bastante coisa", "HORT_FOLHOSAS", None, "verduras", None, None, None, "AUSENTE", "vago"),
    ("12 caixas de tomate maduro, melhor retirar até quinta (08/10).", "HORT_FRUTOS", None, "tomate", 12, "caixa", D(2026, 10, 8), "INFORMADA", ""),
    ("Abóbora cabotiá: 40 unidades. Validade 20/10/2026", "HORT_FRUTOS", None, "abóbora", 40, "unidade", D(2026, 10, 20), "INFORMADA", ""),
    ("Pimentão verde e vermelho, 6 caixas, estragam logo, uns 4 dias", "HORT_FRUTOS", None, "pimentão", 6, "caixa", D(2026, 10, 9), "INFORMADA", "ambigua"),
    ("30 kg de cenoura da horta, validade 15/10.", "HORT_RAIZES", None, "cenoura", 30, "kg", D(2026, 10, 15), "INFORMADA", ""),
    ("500 kg de batata inglesa, validade 05/11", "HORT_RAIZES", None, "batata", 500, "kg", D(2026, 11, 5), "INFORMADA", ""),
    ("Mandioca descascada a vácuo 25 pacotes val. 30/11/26", "HORT_RAIZES", None, "mandioca", 25, "pacote", D(2026, 11, 30), "INFORMADA", ""),
    ("Banana prata, 35 caixas, maduras demais, vencem em 3 dias", "FRUTAS", None, "banana", 35, "caixa", D(2026, 10, 8), "INFORMADA", ""),
    ("Melancia, 60 unidades, vence 14/10", "FRUTAS", None, "melancia", 60, "unidade", D(2026, 10, 14), "INFORMADA", ""),
    ("Mamão, manga e laranja misturados, 10 caixas, vence semana que vem", "FRUTAS", None, "frutas variadas", 10, "caixa", D(2026, 10, 12), "INFORMADA", "ambigua"),
    ("laranja pera 200kg val 12/10/2026", "FRUTAS", None, "laranja", 200, "kg", D(2026, 10, 12), "INFORMADA", ""),
    ("Pão francês do dia, aproximadamente 25 kg, precisa sair hoje", "PANIFICADOS", None, "pão francês", 25, "kg", D(2026, 10, 5), "INFORMADA", ""),
    ("Pães de forma, 60 pacotes, validade impressa 09/10", "PANIFICADOS", None, "pão de forma", 60, "pacote", D(2026, 10, 9), "INFORMADA", ""),
    ("sobras de padaria, 3 caixas", "PANIFICADOS", None, "pães variados", 3, "caixa", None, "INFERIDA_PELA_CATEGORIA", "vago"),
    ("Bolo simples e broa de milho, 40 unidades, feitos hoje de manhã", "PANIFICADOS", None, "bolo simples", 40, "unidade", None, "INFERIDA_PELA_CATEGORIA", ""),
    ("Carne bovina congelada -18°C 300 kg, vence 15/12/2026", "CARNES_PESCADOS", None, "carne bovina", 300, "kg", D(2026, 12, 15), "INFORMADA", ""),
    ("Frango resfriado, 80 kg, usar até sexta 09/10", "CARNES_PESCADOS", None, "frango", 80, "kg", D(2026, 10, 9), "INFORMADA", ""),
    ("Linguiça toscana 50 pacotes mantida a 4 graus, vence em 7 dias", "CARNES_PESCADOS", None, "linguiça", 50, "pacote", D(2026, 10, 12), "INFORMADA", ""),
    ("peixe tilápia congelado 120kg validade 28/02/2027", "CARNES_PESCADOS", None, "peixe", 120, "kg", D(2027, 2, 28), "INFORMADA", ""),
    ("Leite pasteurizado, 200 litros, mantido na geladeira, vence 09/10", "LATICINIOS_OVOS", None, "leite fluido", 200, "litro", D(2026, 10, 9), "INFORMADA", ""),
    ("Queijo mussarela fatiado 30 kg, refrigerado, validade 20/10", "LATICINIOS_OVOS", None, "queijo", 30, "kg", D(2026, 10, 20), "INFORMADA", ""),
    ("ovos brancos - 100 dúzias - vencem 25/10/2026", "LATICINIOS_OVOS", None, "ovos", 100, "duzia", D(2026, 10, 25), "INFORMADA", ""),
    ("Iogurte de morango, 20 caixas, vencimento 12/10", "LATICINIOS_OVOS", None, "iogurte", 20, "caixa", D(2026, 10, 12), "INFORMADA", ""),
    ("Marmitas prontas, 70 unidades, mantidas a 5 graus, consumir até amanhã", "REFEICOES_PRONTAS", None, "marmita", 70, "unidade", D(2026, 10, 6), "INFORMADA", ""),
    ("sopa de legumes, 40 litros, do refeitório de hoje", "REFEICOES_PRONTAS", None, "sopa", 40, "litro", None, "INFERIDA_PELA_CATEGORIA", ""),
    ("120 quentinhas de almoço sem previsão de validade definida", "REFEICOES_PRONTAS", None, "refeição pronta", 120, "unidade", None, "INFERIDA_PELA_CATEGORIA", ""),
    ("Arroz branco tipo 1, 40 pacotes de 5kg, validade 10/03/2027", "GRAOS_CEREAIS", None, "arroz", 40, "pacote", D(2027, 3, 10), "INFORMADA", ""),
    ("Feijão carioca, 800 kg, val. 31/01/2027", "GRAOS_CEREAIS", None, "feijão", 800, "kg", D(2027, 1, 31), "INFORMADA", ""),
    ("fubá e farinha de milho — 25 caixas — validade em 06/2027", "GRAOS_CEREAIS", None, "fubá", 25, "caixa", D(2027, 6, 30), "INFORMADA", "formato_mes_ano"),
    ("Macarrão espaguete 150 pacotes de 500g, vence daqui a uns 5 meses", "GRAOS_CEREAIS", None, "macarrão", 150, "pacote", D(2027, 3, 4), "INFORMADA", "ambigua"),
    ("óleo de soja 60 caixas c/ 20 garrafas, validade 15/08/2027", "INDUSTRIALIZADOS", None, "óleo", 60, "caixa", D(2027, 8, 15), "INFORMADA", ""),
    ("Sardinha em lata, 90 caixas, vence 30/04/27", "INDUSTRIALIZADOS", None, "sardinha em lata", 90, "caixa", D(2027, 4, 30), "INFORMADA", ""),
    ("molho de tomate sachê, 10000 unidades, val 12/2026", "INDUSTRIALIZADOS", None, "molho de tomate", 10000, "unidade", D(2026, 12, 31), "INFORMADA", "formato_mes_ano"),
    ("Açúcar cristal 1000 kg lote com validade 09/2027", "INDUSTRIALIZADOS", None, "açúcar", 1000, "kg", D(2027, 9, 30), "INFORMADA", "formato_mes_ano"),
    ("biscoito recheado, 70 caixas, vence 30/11", "INDUSTRIALIZADOS", None, "biscoito", 70, "caixa", D(2026, 11, 30), "INFORMADA", ""),
    ("Suco de uva integral, 500 litros, validade 15/03/2027", "BEBIDAS", None, "suco de fruta", 500, "litro", D(2027, 3, 15), "INFORMADA", ""),
    ("Água de coco 30 caixas com 12 unidades, val. 14/02/27", "BEBIDAS", None, "água de coco", 30, "caixa", D(2027, 2, 14), "INFORMADA", ""),
    ("Chá gelado em garrafa - 25 caixas - vencimento 20/12/2026", "BEBIDAS", None, "chá pronto", 25, "caixa", D(2026, 12, 20), "INFORMADA", ""),
    ("Temos alimentos diversos para doar, ainda sem separar", "INDEFINIDO", None, None, None, None, None, "AUSENTE", "vago"),
    ("mantimentos variados, umas 10 caixas, não sei a validade", "INDEFINIDO", None, None, 10, "caixa", None, "AUSENTE", "vago"),
    ("cesta com pão francês e leite pasteurizado, 15 cestas, validade 07/10", "PANIFICADOS", "LATICINIOS_OVOS", "pão francês", 15, "unidade", D(2026, 10, 7), "INFORMADA", "duas_categorias"),
    ("frutas e verduras da feira, 12 caixas, vence 08/10", "FRUTAS", "HORT_FOLHOSAS", "frutas variadas", 12, "caixa", D(2026, 10, 8), "INFORMADA", "duas_categorias"),
    ("Alface hidropônica 10 caixas validade 31/12/2027", "HORT_FOLHOSAS", None, "alface", 10, "caixa", D(2027, 12, 31), "INFORMADA", "inconsistente_com_categoria"),
    ("arroz 20 sacos, vence hoje", "GRAOS_CEREAIS", None, "arroz", 20, "unidade", D(2026, 10, 5), "INFORMADA", "inconsistente_com_categoria"),
    ("Leite fluido 50 litros vencido desde 01/10", "LATICINIOS_OVOS", None, "leite fluido", 50, "litro", D(2026, 10, 1), "INFORMADA", "vencido"),
    ("iogurte natural val 04/10/2026 (ontem) 20 caixas", "LATICINIOS_OVOS", None, "iogurte natural", 20, "caixa", D(2026, 10, 4), "INFORMADA", "vencido"),
    ("sobraram 2 bandejas de lasanha, guardadas na geladeira, comer em até 2 dias", "REFEICOES_PRONTAS", None, "lasanha", 2, "bandeja", D(2026, 10, 7), "INFORMADA", ""),
    ("Pão doce e rosca 15kg da manhã", "PANIFICADOS", None, "pão doce", 15, "kg", None, "INFERIDA_PELA_CATEGORIA", ""),
    ("temos 18kg de inhame, dura uns 15 dias", "HORT_RAIZES", None, "inhame", 18, "kg", D(2026, 10, 20), "INFORMADA", "ambigua"),
    ("uvas rubi 70 caixas val 11/10", "FRUTAS", None, "uva", 70, "caixa", D(2026, 10, 11), "INFORMADA", ""),
    ("Peito de frango congelado, validade longa: 14/05/2027, 90 kg", "CARNES_PESCADOS", None, "frango", 90, "kg", D(2027, 5, 14), "INFORMADA", ""),
    ("queijo minas frescal 25 pacotes - atenção: vence amanhã", "LATICINIOS_OVOS", None, "queijo", 25, "pacote", D(2026, 10, 6), "INFORMADA", ""),
    ("requeijão cremoso copo 400g, 300 unidades, val 02/11/2026", "LATICINIOS_OVOS", None, "requeijão", 300, "unidade", D(2026, 11, 2), "INFORMADA", ""),
    ("Salsicha tipo hot dog 60 pacotes mantidos refrigerados vencem 25/10/2026", "CARNES_PESCADOS", None, "salsicha", 60, "pacote", D(2026, 10, 25), "INFORMADA", ""),
    ("goiabada em barra, 200 unidades, validade 03/05/2027", "INDUSTRIALIZADOS", None, "goiabada", 200, "unidade", D(2027, 5, 3), "INFORMADA", ""),
    ("Café torrado e moído 80 pacotes val 15/01/27", "INDUSTRIALIZADOS", None, "café", 80, "pacote", D(2027, 1, 15), "INFORMADA", ""),
    ("Mel puro 150 potes de 500g, validade 02/2028", "INDUSTRIALIZADOS", None, "mel", 150, "unidade", D(2028, 2, 29), "INFORMADA", "formato_mes_ano"),
    ("amendoim torrado 40 kg val 28/02/2027", "INDUSTRIALIZADOS", None, "amendoim", 40, "kg", D(2027, 2, 28), "INFORMADA", ""),
    ("leite em pó integral 1200 pacotes de 400g vence 01/09/2027", "INDUSTRIALIZADOS", None, "leite em pó", 1200, "pacote", D(2027, 9, 1), "INFORMADA", ""),
    ("Aveia em flocos, 60 caixas, val. 18/12/2026", "GRAOS_CEREAIS", None, "aveia", 60, "caixa", D(2026, 12, 18), "INFORMADA", ""),
    ("farinha de trigo 500 kg vence 20/06/2027", "GRAOS_CEREAIS", None, "farinha de trigo", 500, "kg", D(2027, 6, 20), "INFORMADA", ""),
    ("farinha de mandioca 300kg, validade 30/11/2026", "GRAOS_CEREAIS", None, "farinha de mandioca", 300, "kg", D(2026, 11, 30), "INFORMADA", ""),
    ("Brócolis e couve-flor 12 caixas refrigerados, vencem em 3 dias", "HORT_FOLHOSAS", None, "brócolis", 12, "caixa", D(2026, 10, 8), "INFORMADA", ""),
    ("Quiabo 10 caixas até 08/10", "HORT_FRUTOS", None, "quiabo", 10, "caixa", D(2026, 10, 8), "INFORMADA", ""),
    ("cebola roxa 200kg val 30/10", "HORT_RAIZES", None, "cebola", 200, "kg", D(2026, 10, 30), "INFORMADA", ""),
    ("Suco de caixinha 100 caixas de 27 un, vence 15/04/2027", "BEBIDAS", None, "suco de caixinha", 100, "caixa", D(2027, 4, 15), "INFORMADA", ""),
    ("bebida de soja sabor chocolate 40 caixas val 30/03/2027 contém soja", "BEBIDAS", None, "bebida de soja", 40, "caixa", D(2027, 3, 30), "INFORMADA", ""),
    ("Almoço executivo: 90 marmitex, retirar até 14h, validade hoje", "REFEICOES_PRONTAS", None, "marmitex", 90, "unidade", D(2026, 10, 5), "INFORMADA", ""),
    ("Carne moída resfriada 40kg vence em 2 dias", "CARNES_PESCADOS", None, "carne moída", 40, "kg", D(2026, 10, 7), "INFORMADA", ""),
    ("ovos caipiras 30 dúzias vence 18/10", "LATICINIOS_OVOS", None, "ovos", 30, "duzia", D(2026, 10, 18), "INFORMADA", ""),
    ("Mamão formosa 25 caixas, bem maduro, 3 a 4 dias", "FRUTAS", None, "mamão", 25, "caixa", D(2026, 10, 8), "INFORMADA", "ambigua"),
    ("limão tahiti 15 sacos de 20kg val 12/10", "FRUTAS", None, "limão", 15, "unidade", D(2026, 10, 12), "INFORMADA", ""),
    ("Abacaxi pérola, 90 unidades, validade 09/10", "FRUTAS", None, "abacaxi", 90, "unidade", D(2026, 10, 9), "INFORMADA", ""),
    ("Repolho roxo e verde, 150 kg, vence em 6 dias", "HORT_FOLHOSAS", None, "repolho", 150, "kg", D(2026, 10, 11), "INFORMADA", ""),
    ("beterraba lavada 100kg val 22/10", "HORT_RAIZES", None, "beterraba", 100, "kg", D(2026, 10, 22), "INFORMADA", ""),
    ("pepino japonês 8 caixas, vence daqui uns dias", "HORT_FRUTOS", None, "pepino", 8, "caixa", D(2026, 10, 9), "INFORMADA", "ambigua"),
    ("ARROZ 5KG 30 PCT VAL 10/03/27", "GRAOS_CEREAIS", None, "arroz", 30, "pacote", D(2027, 3, 10), "INFORMADA", ""),
    ("tomte 10 cx vence 3 dias", "HORT_FRUTOS", None, "tomate", 10, "caixa", D(2026, 10, 8), "INFORMADA", ""),
    ("iogurt nat 15cx refrigerado 4c val. 12/10", "LATICINIOS_OVOS", None, "iogurte natural", 15, "caixa", D(2026, 10, 12), "INFORMADA", ""),
    ("feijao preto 100kg, val: 10/2027", "GRAOS_CEREAIS", None, "feijão", 100, "kg", D(2027, 10, 31), "INFORMADA", "formato_mes_ano"),
]
COLD_CATS = ("CARNES_PESCADOS", "LATICINIOS_OVOS", "REFEICOES_PRONTAS")
COLD_CUES = ("refriger", "gelad", "congel", "camara fria", "4c", "4 graus", "5 graus", "resfriad", "-18")


def build() -> pd.DataFrame:
    tax = yaml.safe_load(TAXONOMY_FILE.read_text(encoding="utf-8"))["categories"]
    import unicodedata
    rows = []
    for i, (txt, cat, cat2, prod, q, u, exp, src, flags) in enumerate(ITEMS):
        low = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode().lower()
        refrig = None if cat == "INDEFINIDO" else (cat in COLD_CATS or any(c in low for c in COLD_CUES))
        rows.append({"text_id": f"P{i:03d}", "texto": txt, "reference_date": str(REF), "y_categoria": cat, "y_categoria_2": cat2, "y_produto": prod,
                     "y_perecibilidade": None if cat == "INDEFINIDO" else tax[cat]["perecibilidade"], "y_exige_refrigeracao": refrig,
                     "y_dias_ate_validade": (exp - REF).days if exp else None, "y_validity_source": src, "y_quantidade": q, "y_unidade": u,
                     "difficulty_flags": flags, "data_origin": "SIMULATED", "authoring": "IA_RASCUNHO_PROVISORIO_REVISAO_PENDENTE"})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[2] / "data" / "manual_labeled"
    out.mkdir(parents=True, exist_ok=True)
    df = build()
    df.to_csv(out / "PROVISORIO_rascunho_ia.csv", sep=";", index=False, encoding="utf-8")
    cols = [c for c in df.columns if c not in ("data_origin", "authoring")] + ["data_origin", "annotator_a", "annotator_b", "adjudicado_por", "frozen_at"]
    pd.DataFrame(columns=cols).to_csv(out / "manual_labeled_text_TEMPLATE.csv", sep=";", index=False, encoding="utf-8")
    print(len(df), "textos provisórios;", df.y_categoria.value_counts().to_dict())
