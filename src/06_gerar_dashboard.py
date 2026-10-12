"""
ETAPA 6 - DASHBOARD HTML
========================

Gera dashboard/painel_frota.html: uma página única, sem servidor, que abre em
qualquer navegador. Os dados vão embutidos no próprio arquivo em formato JSON
e os gráficos são desenhados com a biblioteca JavaScript Chart.js.

O Python prepara um "cubo" pequeno (mês x filial x tipo de veículo) com as
somas já calculadas. O JavaScript da página só filtra e soma esse cubo quando
o usuário troca a filial ou o período. É a mesma ideia de uma tabela agregada
no Power BI: o painel fica leve porque não carrega as 54 mil linhas de pedágio.

Como rodar:  python src/06_gerar_dashboard.py
"""

import json

import numpy as np
import pandas as pd

from utils import OUTPUTS, RAIZ

PBI = RAIZ / "powerbi"
TEMPLATE = RAIZ / "src" / "dashboard_template.html"
SAIDA = RAIZ / "dashboard" / "painel_frota.html"


def ler(nome: str) -> pd.DataFrame:
    return pd.read_csv(PBI / f"{nome}.csv", sep=";", decimal=",", encoding="utf-8-sig")


veic = ler("dim_veiculo")
mot = ler("dim_motorista")
viagens = ler("fato_viagens")
abast = ler("fato_abastecimentos")
ped = ler("fato_pedagios")

chave = ["mes", "filial", "tipo"]
info_veic = veic[["placa", "filial", "tipo_veiculo", "km_l_referencia", "eixos_suspensiveis"]].rename(
    columns={"tipo_veiculo": "tipo"})


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.merge(info_veic, on="placa", how="left")
    df["mes"] = df["data"].str[:7]
    return df


viagens, abast, ped = preparar(viagens), preparar(abast), preparar(ped)

# --- Agregações por mês x filial x tipo ---------------------------------------
cubo_viagens = viagens.groupby(chave).agg(km=("km_rodado", "sum"), viagens=("id_viagem", "count"))

abast["km_esperado_litros"] = abast["km_desde_ultimo"] / abast["km_l_referencia"]
valido = abast["km_desde_ultimo"].notna()
# Litros acima do que o consumo de referência (com 10% de folga) justificaria
critico = valido & (abast["km_l_real"] < abast["km_l_referencia"] * 0.80)
abast["excesso_rs"] = np.where(
    critico,
    (abast["litros"] - abast["km_desde_ultimo"] / (abast["km_l_referencia"] * 0.90)) * abast["preco_litro"],
    0)
abast["km_valido"] = abast["km_desde_ultimo"].where(valido, 0)
abast["litros_valido"] = abast["litros"].where(valido, 0)
abast["n_excesso"] = critico.astype(int)
cubo_abast = abast.groupby(chave).agg(
    litros=("litros", "sum"), comb=("valor_total", "sum"),
    km_valido=("km_valido", "sum"), litros_valido=("litros_valido", "sum"),
    km_esp_litros=("km_esperado_litros", "sum"),
    excesso=("excesso_rs", "sum"), n_excesso=("n_excesso", "sum"))

elegivel = (ped["status_carga"] == "VAZIO") & (ped["eixos_suspensiveis"] > 0)
ped["eleg"] = elegivel.astype(int)
ped["nao_susp"] = (ped["perda_eixo_nao_suspenso"] > 0).astype(int)
ped["dup_rs"] = ped["valor_transacao"] * ped["flag_cobranca_duplicada"]
cubo_ped = ped.groupby(chave).agg(
    ped=("valor_transacao", "sum"), perda_eixo=("perda_eixo_nao_suspenso", "sum"),
    eleg=("eleg", "sum"), nao_susp=("nao_susp", "sum"),
    dup=("dup_rs", "sum"), n_dup=("flag_cobranca_duplicada", "sum"))

cubo = cubo_viagens.join(cubo_abast, how="outer").join(cubo_ped, how="outer").fillna(0).reset_index()
cubo = cubo.round(2)

# --- Listas para as tabelas ---------------------------------------------------
anom = pd.read_csv(OUTPUTS / "anomalias_abastecimento.csv").merge(
    veic[["placa", "filial"]], on="placa").merge(mot[["id_motorista", "nome"]], on="id_motorista")
anom["mes"] = anom["data_hora"].str[:7]
auditoria = anom[["data_hora", "mes", "placa", "tipo_veiculo", "filial", "nome", "litros",
                  "km_l_real", "km_l_referencia", "qtd_metodos", "score_anomalia"]]

motoristas = pd.read_csv(OUTPUTS / "consultas" / "q09_ranking_motoristas.csv")
metodos = pd.read_csv(OUTPUTS / "comparacao_metodos.csv")

dados = {
    "colunas": list(cubo.columns),
    "cubo": cubo.values.tolist(),
    "auditoria": auditoria.round(3).to_dict(orient="records"),
    "motoristas": motoristas.round(3).fillna(0).to_dict(orient="records"),
    "metodos": metodos.to_dict(orient="records"),
    "fraudes_gabarito": int(pd.read_csv(RAIZ / "data" / "gabarito_fraudes.csv")["fraude"].sum()),
}

html = TEMPLATE.read_text(encoding="utf-8").replace(
    "/*__DADOS__*/null", json.dumps(dados, ensure_ascii=False, separators=(",", ":")))
# Envolve o conteúdo num documento HTML completo (doctype, charset e idioma)
html = ('<!doctype html>\n<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n'
        + html.replace('<div class="wrap">', '</head>\n<body>\n<div class="wrap">', 1)
        + "</body>\n</html>\n")
SAIDA.parent.mkdir(exist_ok=True)
SAIDA.write_text(html, encoding="utf-8")
# Cópia em docs/index.html: é a pasta que o GitHub Pages publica como site
PAGES = RAIZ / "docs" / "index.html"
PAGES.parent.mkdir(exist_ok=True)
PAGES.write_text(html, encoding="utf-8")
print(f"Dashboard gerado: {SAIDA} ({SAIDA.stat().st_size / 1024:.0f} KB) e copiado para {PAGES}")
