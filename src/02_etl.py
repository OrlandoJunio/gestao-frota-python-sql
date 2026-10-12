"""
ETAPA 1 e 2 - ETL: EXTRAIR, TRATAR E CARREGAR NO BANCO SQLITE
=============================================================

ETL = Extract, Transform, Load. É o que o Power Query faz no Power BI,
só que aqui escrito em Python com a biblioteca pandas.

    EXTRACT   -> ler os CSVs brutos de data/raw/
    TRANSFORM -> padronizar placas, converter datas, remover duplicadas,
                 preencher centro de custo vazio, marcar dados suspeitos
    LOAD      -> gravar tudo no banco data/frotas.db (SQLite)

No fim, gera outputs/relatorio_qualidade.md com o que foi encontrado e
corrigido. "Validar qualidade de dados e pipelines" é uma das atividades
da vaga, e este relatório é a prova disso.

Como rodar:  python src/02_etl.py
"""

import re
import sqlite3
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
PASTA_RAW = RAIZ / "data" / "raw"
BANCO = RAIZ / "data" / "frotas.db"
SCHEMA = RAIZ / "sql" / "01_criar_tabelas.sql"
RELATORIO = RAIZ / "outputs" / "relatorio_qualidade.md"

# Vamos guardar cada verificação de qualidade nesta lista para montar o relatório.
log_qualidade: list[tuple[str, str, int]] = []


def registrar(tabela: str, verificacao: str, qtd: int) -> None:
    log_qualidade.append((tabela, verificacao, int(qtd)))
    print(f"  [{tabela}] {verificacao}: {qtd}")


# =============================================================================
# EXTRACT
# =============================================================================
print("1) Lendo CSVs brutos...")
frotas = pd.read_csv(PASTA_RAW / "frotas.csv")
motoristas = pd.read_csv(PASTA_RAW / "motoristas.csv")
viagens = pd.read_csv(PASTA_RAW / "viagens.csv")
# O cartão combustível exporta no padrão brasileiro: separador ";" e vírgula decimal.
# Sem informar isso, o pandas leria "168,72" como texto e não como número.
abast = pd.read_csv(PASTA_RAW / "abastecimentos.csv", sep=";", decimal=",")
pedagios = pd.read_csv(PASTA_RAW / "pedagios.csv")

for nome, df in [("frotas", frotas), ("motoristas", motoristas), ("viagens", viagens),
                 ("abastecimentos", abast), ("pedagios", pedagios)]:
    registrar(nome, "linhas lidas do CSV", len(df))

# =============================================================================
# TRANSFORM
# =============================================================================
print("2) Tratando os dados...")


# --- 2.1 Padronizar placas ----------------------------------------------------
def padronizar_placa(placa: str) -> str:
    """' abc-1d23 ' -> 'ABC1D23'. Tira espaços, hífen e deixa maiúsculo."""
    return re.sub(r"[^A-Z0-9]", "", str(placa).upper())


for nome, df in [("abastecimentos", abast), ("pedagios", pedagios)]:
    antes = df["placa"].copy()
    df["placa"] = df["placa"].apply(padronizar_placa)
    registrar(nome, "placas corrigidas (minúscula/hífen/espaço)", (antes != df["placa"]).sum())

# --- 2.2 Converter texto em data ---------------------------------------------
# Cada sistema exporta a data num formato. Informar o formato evita que o pandas
# confunda 03/04 (3 de abril) com 4 de março.
abast["data_hora"] = pd.to_datetime(abast["data_hora"], format="%d/%m/%Y %H:%M")
pedagios["data_hora_passagem"] = pd.to_datetime(pedagios["data_hora_passagem"], format="%d/%m/%Y %H:%M:%S")
viagens["data_hora_saida"] = pd.to_datetime(viagens["data_hora_saida"], format="%Y-%m-%d %H:%M")
viagens["data_hora_chegada"] = pd.to_datetime(viagens["data_hora_chegada"], format="%Y-%m-%d %H:%M")

# --- 2.3 Duplicadas de exportação no pedágio ---------------------------------
# Linha inteira repetida com o MESMO id_transacao = erro de exportação -> remover.
# (Cobranças em duplicidade com ids DIFERENTES são outra história: são um
#  problema de negócio e serão investigadas em SQL, não apagadas aqui.)
qtd_dup = pedagios.duplicated(subset="id_transacao").sum()
pedagios = pedagios.drop_duplicates(subset="id_transacao", keep="first")
registrar("pedagios", "linhas duplicadas removidas (mesmo id_transacao)", qtd_dup)

# --- 2.4 Centro de custo vazio -> buscar no cadastro da frota ----------------
# É um "PROCV"/merge: para cada placa, pegamos o centro de custo do cadastro.
vazios = pedagios["centro_custo"].isna()
mapa_cc = frotas.set_index("placa")["centro_custo"]
pedagios.loc[vazios, "centro_custo"] = pedagios.loc[vazios, "placa"].map(mapa_cc)
registrar("pedagios", "centro de custo vazio preenchido pelo cadastro", vazios.sum())

# --- 2.5 Placas que não existem no cadastro ----------------------------------
for nome, df in [("abastecimentos", abast), ("pedagios", pedagios), ("viagens", viagens)]:
    orfas = ~df["placa"].isin(frotas["placa"])
    registrar(nome, "placas fora do cadastro de frota", orfas.sum())

# --- 2.6 Abastecimento: litros acima da capacidade do tanque -----------------
abast = abast.merge(frotas[["placa", "capacidade_tanque_l"]], on="placa", how="left")
abast["flag_litros_acima_tanque"] = (abast["litros"] > abast["capacidade_tanque_l"]).astype(int)
registrar("abastecimentos", "litros acima da capacidade do tanque (flag)", abast["flag_litros_acima_tanque"].sum())
abast = abast.drop(columns="capacidade_tanque_l")

# --- 2.7 Abastecimento: hodômetro inconsistente ------------------------------
# Ordenamos por placa e data e comparamos cada hodômetro com o anterior da mesma
# placa. groupby + diff() faz exatamente isso (é a ideia do LAG em SQL).
# Se o hodômetro "andou para trás" ou saltou mais de 5.000 km, é erro de digitação.
abast = abast.sort_values(["placa", "data_hora"]).reset_index(drop=True)
variacao = abast.groupby("placa")["hodometro"].diff()
abast["flag_hodometro_inconsistente"] = ((variacao < 0) | (variacao > 5000)).astype(int)
registrar("abastecimentos", "hodômetro inconsistente (flag)", abast["flag_hodometro_inconsistente"].sum())

# --- 2.8 Valores nulos restantes ----------------------------------------------
for nome, df in [("abastecimentos", abast), ("pedagios", pedagios), ("viagens", viagens)]:
    registrar(nome, "células nulas após tratamento", df.isna().sum().sum())


# =============================================================================
# LOAD
# =============================================================================
print("3) Carregando no SQLite...")


def para_texto_iso(serie: pd.Series) -> pd.Series:
    """SQLite não tem tipo data: guardamos como texto 'AAAA-MM-DD HH:MM:SS' (ordena certo)."""
    return serie.dt.strftime("%Y-%m-%d %H:%M:%S")


abast["data_hora"] = para_texto_iso(abast["data_hora"])
pedagios["data_hora_passagem"] = para_texto_iso(pedagios["data_hora_passagem"])
viagens["data_hora_saida"] = para_texto_iso(viagens["data_hora_saida"])
viagens["data_hora_chegada"] = para_texto_iso(viagens["data_hora_chegada"])

BANCO.parent.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(BANCO) as con:
    # Cria as tabelas a partir do arquivo .sql (schema com chaves e índices)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))

    # if_exists="append": as tabelas já existem (criadas acima), só inserimos as linhas.
    # A ordem importa por causa das chaves estrangeiras: primeiro as dimensões.
    for nome, df in [("motoristas", motoristas), ("frotas", frotas), ("viagens", viagens),
                     ("abastecimentos", abast), ("pedagios", pedagios)]:
        df.to_sql(nome, con, if_exists="append", index=False)
        total = con.execute(f"SELECT COUNT(*) FROM {nome}").fetchone()[0]
        registrar(nome, "linhas gravadas no banco", total)

    # Confere se alguma chave estrangeira ficou quebrada
    problemas_fk = con.execute("PRAGMA foreign_key_check").fetchall()
    registrar("banco", "violações de chave estrangeira", len(problemas_fk))

# =============================================================================
# RELATÓRIO DE QUALIDADE
# =============================================================================
RELATORIO.parent.mkdir(parents=True, exist_ok=True)
linhas = ["# Relatório de qualidade de dados (ETL)", "",
          "Gerado por `src/02_etl.py`.", "",
          "| Tabela | Verificação | Quantidade |", "|---|---|---:|"]
linhas += [f"| {t} | {v} | {q:,} |".replace(",", ".") for t, v, q in log_qualidade]
RELATORIO.write_text("\n".join(linhas) + "\n", encoding="utf-8")
print(f"\nBanco pronto em {BANCO}\nRelatório em {RELATORIO}")
