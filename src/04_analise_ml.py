"""
ETAPA 4 - ANÁLISE EM PYTHON E DETECÇÃO DE ANOMALIAS (MACHINE LEARNING)
======================================================================

Pergunta de negócio: "quais abastecimentos parecem fora do padrão e merecem
ser auditados?" (desvio de combustível, abastecimento de galão, cartão usado
em outro veículo...)

Comparamos três abordagens, da mais simples para a mais sofisticada:

  1. REGRA FIXA (a consulta q08 em SQL): km/l abaixo de 80% da referência
     ou litros acima do tanque.
  2. Z-SCORE: estatística simples. Para cada veículo, mede quantos desvios
     padrão o km/l de um abastecimento está abaixo da média DAQUELE veículo.
  3. ISOLATION FOREST (scikit-learn): modelo de Machine Learning não
     supervisionado. Ele olha várias variáveis ao mesmo tempo e isola os
     pontos "estranhos". Não precisa de exemplos rotulados de fraude.

Como os dados são fictícios, temos um gabarito (data/gabarito_fraudes.csv)
e conseguimos MEDIR quem acerta mais. No mundo real não existe gabarito:
os casos apontados iriam para auditoria, e o resultado da auditoria viraria
o rótulo para um modelo supervisionado no futuro.

Saídas:
    outputs/anomalias_abastecimento.csv
    outputs/comparacao_metodos.csv
    outputs/graficos/*.png

Como rodar:  python src/04_analise_ml.py
"""

import sqlite3

import matplotlib
matplotlib.use("Agg")  # gera imagens sem precisar de tela
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import precision_score, recall_score
from sklearn.preprocessing import StandardScaler

from utils import BANCO, OUTPUTS, RAIZ, carregar_consultas

GRAFICOS = OUTPUTS / "graficos"
GRAFICOS.mkdir(parents=True, exist_ok=True)

# Paleta (validada para daltonismo) e cores de "status"
AZUL, LARANJA, VERDE_AGUA = "#2a78d6", "#eb6834", "#1baf7a"
CINZA, TEXTO, TEXTO_2, GRADE = "#c3c2b7", "#0b0b0b", "#52514e", "#e1e0d9"
CRITICO = "#d03b3b"

plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
    "axes.edgecolor": CINZA, "axes.labelcolor": TEXTO_2, "text.color": TEXTO,
    "xtick.color": TEXTO_2, "ytick.color": TEXTO_2,
    "axes.grid": True, "grid.color": GRADE, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 10, "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.titlelocation": "left",
})


def brl(valor: float) -> str:
    """Formata 1234567.8 como 'R$ 1.234.568'."""
    return "R$ " + f"{valor:,.0f}".replace(",", ".")


# =============================================================================
# 1. Carregar dados do banco
# =============================================================================
consultas = carregar_consultas()
with sqlite3.connect(BANCO) as con:
    # Reaproveitamos a consulta q05 (km/l por abastecimento com LAG) direto do .sql
    abast = pd.read_sql(consultas["q05_km_por_litro_por_abastecimento"], con)
    frotas = pd.read_sql("SELECT placa, capacidade_tanque_l, filial FROM frotas", con)
    regra = pd.read_sql(consultas["q08_abastecimentos_suspeitos_regra"], con)
    mensal = pd.read_sql(consultas["q02_custo_mensal_centro_custo"], con)
    eixo = pd.read_sql(consultas["q04_retorno_vazio_sem_eixo_suspenso"], con)
    modelos = pd.read_sql(consultas["q06_km_l_por_modelo"], con)

abast = abast.merge(frotas, on="placa", how="left")
print(f"Abastecimentos com km/l calculado: {len(abast):,}")

# =============================================================================
# 2. Engenharia de variáveis (features)
# =============================================================================
# O modelo não entende "placa" ou "tipo de veículo"; ele precisa de números que
# sejam comparáveis entre um Toco e um Rodotrem. Por isso usamos proporções:
abast["razao_kml"] = abast["km_l_real"] / abast["km_l_referencia"]      # 1.0 = consumo esperado
abast["pct_tanque"] = abast["litros"] / abast["capacidade_tanque_l"]    # quanto do tanque encheu
# Autonomia usada: km rodados / km que um tanque cheio deveria fazer
abast["pct_autonomia"] = abast["km_desde_ultimo"] / (abast["capacidade_tanque_l"] * abast["km_l_referencia"])

# =============================================================================
# 3. Método 2 - Z-score por veículo
# =============================================================================
# z = (valor - média do veículo) / desvio padrão do veículo
# transform() devolve o resultado com o mesmo tamanho da tabela original.
grupo = abast.groupby("placa")["km_l_real"]
abast["zscore_kml"] = (abast["km_l_real"] - grupo.transform("mean")) / grupo.transform("std")
abast["anomalia_zscore"] = (abast["zscore_kml"] < -2.5).astype(int)   # só nos interessa o lado "consumiu demais"

# =============================================================================
# 4. Método 3 - Isolation Forest
# =============================================================================
features = ["razao_kml", "pct_tanque", "pct_autonomia"]
X = StandardScaler().fit_transform(abast[features])  # coloca as variáveis na mesma escala

# contamination = % esperado de anomalias. Começamos com 2%, um chute típico de auditoria.
modelo = IsolationForest(n_estimators=300, contamination=0.02, random_state=42)
abast["anomalia_iforest"] = (modelo.fit_predict(X) == -1).astype(int)   # -1 = anomalia
abast["score_anomalia"] = -modelo.score_samples(X)                      # quanto maior, mais estranho
# O Isolation Forest marca os dois extremos. Consumo MELHOR que o esperado não é
# fraude, então só mantemos as anomalias em que o km/l ficou abaixo da referência.
abast.loc[abast["razao_kml"] >= 1, "anomalia_iforest"] = 0

# Método 1 - regra SQL (já calculada na q08)
abast["anomalia_regra"] = abast["id_abastecimento"].isin(regra["id_abastecimento"]).astype(int)

# =============================================================================
# 5. Comparação com o gabarito
# =============================================================================
gabarito = pd.read_csv(RAIZ / "data" / "gabarito_fraudes.csv")
abast = abast.merge(gabarito, on="id_abastecimento", how="left")

# Consenso: só entra na lista quem foi apontado por pelo menos 2 dos 3 métodos.
# Cada método erra de um jeito diferente; quando dois concordam, a chance de ser
# fraude de verdade sobe muito (é a ideia de "ensemble" em Machine Learning).
abast["qtd_metodos"] = abast[["anomalia_regra", "anomalia_zscore", "anomalia_iforest"]].sum(axis=1)
abast["anomalia_consenso"] = (abast["qtd_metodos"] >= 2).astype(int)

linhas = []
for nome, coluna in [("Regra fixa (SQL q08)", "anomalia_regra"),
                     ("Z-score por veículo", "anomalia_zscore"),
                     ("Isolation Forest", "anomalia_iforest"),
                     ("Consenso (2 ou mais métodos)", "anomalia_consenso")]:
    linhas.append({
        "metodo": nome,
        "casos_apontados": int(abast[coluna].sum()),
        # Precisão: dos casos apontados, quantos eram fraude de verdade?
        "precisao": round(precision_score(abast["fraude"], abast[coluna]), 3),
        # Recall: das fraudes que existiam, quantas o método encontrou?
        "recall": round(recall_score(abast["fraude"], abast[coluna]), 3),
    })
comparacao = pd.DataFrame(linhas)
comparacao.to_csv(OUTPUTS / "comparacao_metodos.csv", index=False)
print("\nComparação dos métodos (fraudes no gabarito:", int(abast["fraude"].sum()), ")")
print(comparacao.to_string(index=False))

# Lista final para auditoria: apontado por qualquer método, ordenado por quantos
# métodos concordam e depois pelo score do modelo (prioridade de auditoria).
auditoria = (abast[abast["qtd_metodos"] > 0]
             .sort_values(["qtd_metodos", "score_anomalia"], ascending=False)
             [["id_abastecimento", "data_hora", "placa", "tipo_veiculo", "id_motorista", "litros",
               "valor_total", "km_l_real", "km_l_referencia", "razao_kml", "pct_tanque",
               "zscore_kml", "score_anomalia", "anomalia_regra", "anomalia_zscore",
               "anomalia_iforest", "qtd_metodos"]])
auditoria.round(3).to_csv(OUTPUTS / "anomalias_abastecimento.csv", index=False)
print(f"\nLista de auditoria: {len(auditoria)} abastecimentos")

print("\nMotoristas com mais anomalias (Isolation Forest):")
print(abast.groupby("id_motorista")["anomalia_iforest"].sum().sort_values(ascending=False).head(6).to_string())

# =============================================================================
# 6. Gráficos (os mesmos que fariamos no Power BI)
# =============================================================================

# 6.1 Custo mensal: combustível x pedágio ------------------------------------
m = mensal.groupby("mes")[["combustivel", "pedagio"]].sum() / 1000
fig, ax = plt.subplots(figsize=(10, 4.5))
ax.bar(m.index, m["combustivel"], color=AZUL, width=0.7, label="Combustível")
ax.bar(m.index, m["pedagio"], bottom=m["combustivel"], color=LARANJA, width=0.7, label="Pedágio",
       edgecolor="#fcfcfb", linewidth=2)
ax.set_title("Custo mensal da operação (R$ mil)")
ax.set_ylabel("R$ mil")
ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0), ncols=2)
ax.set_title("Custo mensal da operação (R$ mil)", pad=28)
ax.grid(axis="x", visible=False)
plt.xticks(rotation=45)
fig.tight_layout()
fig.savefig(GRAFICOS / "01_custo_mensal.png", dpi=150)
plt.close(fig)

# 6.2 km/l real x referência por modelo --------------------------------------
mod = modelos.assign(rotulo=modelos["tipo_veiculo"] + " | " + modelos["modelo"]).sort_values("desvio_pct")
fig, ax = plt.subplots(figsize=(10, 5.5))
ax.barh(mod["rotulo"], mod["desvio_pct"], color=AZUL, height=0.6)
ax.axvline(0, color=TEXTO_2, linewidth=1)
ax.set_xlim(mod["desvio_pct"].min() * 1.18, 0)
for y, v in enumerate(mod["desvio_pct"]):
    ax.text(v - 0.3, y, f"{v:.1f}%", va="center", ha="right", color=TEXTO_2, fontsize=9)
ax.set_title("km/l real vs. referência, por modelo (desvio %)")
ax.set_xlabel("Desvio em relação ao km/l de referência (%)")
ax.grid(axis="y", visible=False)
fig.tight_layout()
fig.savefig(GRAFICOS / "02_kml_por_modelo.png", dpi=150)
plt.close(fig)

# 6.3 Dispersão das anomalias -------------------------------------------------
fig, ax = plt.subplots(figsize=(9, 5.5))
normal = abast[abast["anomalia_iforest"] == 0]
anom = abast[abast["anomalia_iforest"] == 1]
ax.scatter(normal["pct_tanque"] * 100, normal["razao_kml"] * 100, s=10, color=CINZA, alpha=0.6,
           label="Normal")
ax.scatter(anom["pct_tanque"] * 100, anom["razao_kml"] * 100, s=28, color=CRITICO,
           edgecolor="#fcfcfb", linewidth=1, label="Anomalia (Isolation Forest)")
ax.axhline(80, color=TEXTO_2, linewidth=1)
ax.text(ax.get_xlim()[1] - 1, 81,  "regra fixa: 80% do km/l esperado", color=TEXTO_2, fontsize=9, ha="right")
ax.set_title("Abastecimentos: % do tanque abastecido x km/l obtido")
ax.set_xlabel("Litros abastecidos (% da capacidade do tanque)")
ax.set_ylabel("km/l real (% da referência)")
ax.legend(frameon=False, loc="lower left")
fig.tight_layout()
fig.savefig(GRAFICOS / "03_anomalias_abastecimento.png", dpi=150)
plt.close(fig)

# 6.4 Perda com eixo não suspenso, por filial --------------------------------
p = eixo.groupby("filial")["perda_estimada"].sum().sort_values()
fig, ax = plt.subplots(figsize=(9, 4))
ax.barh(p.index, p.values, color=AZUL, height=0.55)
for y, v in enumerate(p.values):
    ax.text(v, y, "  " + brl(v), va="center", color=TEXTO_2, fontsize=9)
ax.set_title("Pedágio pago a mais em retorno vazio sem suspender eixo")
ax.set_xlabel("R$ no período")
ax.set_xlim(0, p.max() * 1.2)
ax.grid(axis="y", visible=False)
fig.tight_layout()
fig.savefig(GRAFICOS / "04_perda_eixo_por_filial.png", dpi=150)
plt.close(fig)

print(f"\nGráficos salvos em {GRAFICOS}")
