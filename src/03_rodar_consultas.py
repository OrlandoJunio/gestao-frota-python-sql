"""
ETAPA 3 - EXECUTAR AS CONSULTAS SQL DE NEGÓCIO
==============================================

Lê sql/02_consultas_negocio.sql, separa cada consulta pela marcação
"-- @consulta: nome", executa no banco e salva o resultado em
outputs/consultas/<nome>.csv. Também mostra as primeiras linhas na tela.

Isso mostra um padrão muito comum no trabalho: o SQL fica num arquivo .sql
(fácil de revisar e versionar) e o Python só orquestra a execução.

Como rodar:  python src/03_rodar_consultas.py
"""

import sqlite3
import time

import pandas as pd

from utils import BANCO, OUTPUTS, carregar_consultas

SAIDA = OUTPUTS / "consultas"
SAIDA.mkdir(parents=True, exist_ok=True)

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 12)

with sqlite3.connect(BANCO) as con:
    for nome, sql in carregar_consultas().items():
        inicio = time.perf_counter()
        # pd.read_sql executa a consulta e já devolve um DataFrame
        resultado = pd.read_sql(sql, con)
        segundos = time.perf_counter() - inicio
        resultado.to_csv(SAIDA / f"{nome}.csv", index=False)
        print(f"\n=== {nome}  ({len(resultado):,} linhas, {segundos:.2f}s) ===")
        print(resultado.head(5).to_string(index=False))

print(f"\nResultados salvos em {SAIDA}")
