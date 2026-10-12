"""
Roda o projeto inteiro, na ordem, com um único comando:

    python rodar_pipeline.py

Cada etapa é um script independente em src/. Se uma falhar, o pipeline para
e mostra o erro (é assim que um orquestrador como o Airflow pensa, em miniatura).
"""

import subprocess
import sys
import time
from pathlib import Path

ETAPAS = [
    ("Gerar dados fictícios", "01_gerar_dados.py"),
    ("ETL: tratar e carregar no SQLite", "02_etl.py"),
    ("Consultas SQL de negócio", "03_rodar_consultas.py"),
    ("Análise e Machine Learning", "04_analise_ml.py"),
    ("Exportar modelo para Power BI", "05_exportar_powerbi.py"),
    ("Gerar dashboard HTML", "06_gerar_dashboard.py"),
]

SRC = Path(__file__).resolve().parent / "src"

for i, (nome, script) in enumerate(ETAPAS, start=1):
    print(f"\n{'=' * 70}\n[{i}/{len(ETAPAS)}] {nome}\n{'=' * 70}")
    inicio = time.perf_counter()
    resultado = subprocess.run([sys.executable, script], cwd=SRC)
    if resultado.returncode != 0:
        sys.exit(f"\nFalhou na etapa '{nome}'. Corrija o erro acima e rode de novo.")
    print(f"-> ok em {time.perf_counter() - inicio:.1f}s")

print("\nPronto! Abra dashboard/painel_frota.html no navegador.")
