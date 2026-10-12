"""
ETAPA 5 - EXPORTAR UM MODELO ESTRELA PARA O POWER BI
====================================================

O Power BI funciona melhor com um "modelo estrela" (star schema):
tabelas de DIMENSÃO (quem/onde/quando: veículo, motorista, calendário) ligadas
a tabelas FATO (o que aconteceu: viagens, abastecimentos, pedágios).

Aqui o SQL faz o trabalho pesado que normalmente ficaria no Power Query:
    * o pedágio já sai ligado à viagem (e portanto ao status CARREGADO/VAZIO)
    * a perda por eixo não suspenso e a cobrança duplicada já vêm calculadas
    * o abastecimento já vem com km/l real e a marcação de anomalia do modelo de ML

Os CSVs saem no padrão brasileiro (";" e vírgula decimal, UTF-8 com BOM),
que o Power BI em português lê sem configurar nada.

Como rodar:  python src/05_exportar_powerbi.py
"""

import sqlite3

import pandas as pd

from utils import BANCO, OUTPUTS, RAIZ, carregar_consultas

PASTA_PBI = RAIZ / "powerbi"
PASTA_PBI.mkdir(exist_ok=True)
consultas = carregar_consultas()

SQL = {
    "dim_veiculo": """
        SELECT placa, tag, tipo_veiculo, marca, modelo, ano_fabricacao, qtd_eixos,
               eixos_suspensiveis, km_l_referencia, capacidade_tanque_l,
               filial, centro_custo, id_motorista_titular
        FROM frotas
    """,
    "dim_motorista": "SELECT id_motorista, nome, filial, data_admissao FROM motoristas",
    "fato_viagens": """
        SELECT id_viagem, placa, id_motorista, origem, destino,
               date(data_hora_saida) AS data, data_hora_saida, data_hora_chegada,
               km_rodado, status_carga, peso_carga_kg
        FROM viagens
    """,
    # Pedágio enriquecido: viagem, status de carga, perda por eixo e duplicidade
    "fato_pedagios": """
        WITH base AS (
            SELECT p.*,
                   LAG(p.data_hora_passagem) OVER (PARTITION BY p.placa, p.codigo_praca
                                                   ORDER BY p.data_hora_passagem) AS anterior
            FROM pedagios p
        )
        SELECT b.id_transacao, date(b.data_hora_passagem) AS data, b.data_hora_passagem,
               b.placa, b.tag, b.praca, b.rodovia, b.concessionaria,
               b.categoria_eixos, b.valor_transacao, b.centro_custo,
               v.id_viagem, v.id_motorista, v.status_carga,
               CASE WHEN v.status_carga = 'VAZIO' AND f.eixos_suspensiveis > 0
                         AND b.categoria_eixos = f.qtd_eixos
                    THEN ROUND(b.valor_transacao / b.categoria_eixos * f.eixos_suspensiveis, 2)
                    ELSE 0 END AS perda_eixo_nao_suspenso,
               CASE WHEN (julianday(b.data_hora_passagem) - julianday(b.anterior)) * 1440 < 10
                    THEN 1 ELSE 0 END AS flag_cobranca_duplicada
        FROM base b
        JOIN frotas f ON f.placa = b.placa
        LEFT JOIN viagens v ON v.placa = b.placa
              AND b.data_hora_passagem BETWEEN v.data_hora_saida AND v.data_hora_chegada
    """,
}

with sqlite3.connect(BANCO) as con:
    tabelas = {nome: pd.read_sql(sql, con) for nome, sql in SQL.items()}
    abast_todos = pd.read_sql("SELECT * FROM abastecimentos", con)
    kml = pd.read_sql(consultas["q05_km_por_litro_por_abastecimento"], con)

# Abastecimentos: todos os registros + km/l (quando calculável) + resultado do ML
anomalias = pd.read_csv(OUTPUTS / "anomalias_abastecimento.csv")
fato_abast = (abast_todos
              .merge(kml[["id_abastecimento", "km_desde_ultimo", "km_l_real", "faixa_consumo"]],
                     on="id_abastecimento", how="left")
              .merge(anomalias[["id_abastecimento", "qtd_metodos", "score_anomalia"]],
                     on="id_abastecimento", how="left"))
fato_abast["qtd_metodos"] = fato_abast["qtd_metodos"].fillna(0).astype(int)
fato_abast["prioridade_auditoria"] = fato_abast["qtd_metodos"].map(
    {0: "Sem alerta", 1: "Baixa", 2: "Alta", 3: "Alta"})
fato_abast.insert(1, "data", pd.to_datetime(fato_abast["data_hora"]).dt.date)
tabelas["fato_abastecimentos"] = fato_abast

# Calendário: no Power BI a tabela de datas é obrigatória para inteligência de tempo
datas = pd.date_range("2025-10-01", "2026-09-30", freq="D")
meses_pt = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
tabelas["dim_calendario"] = pd.DataFrame({
    "data": datas.date,
    "ano": datas.year,
    "mes_num": datas.month,
    "mes_nome": [meses_pt[m - 1] for m in datas.month],
    "ano_mes": datas.strftime("%Y-%m"),
    "trimestre": "T" + datas.quarter.astype(str),
    "dia_semana": datas.dayofweek + 1,
})

for nome, df in tabelas.items():
    df.to_csv(PASTA_PBI / f"{nome}.csv", sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print(f"  {nome:22s} {len(df):>7,} linhas")
print(f"\nCSVs para Power BI em {PASTA_PBI}")
