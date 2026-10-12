"""Funções e caminhos compartilhados pelos scripts do projeto."""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
BANCO = RAIZ / "data" / "frotas.db"
ARQUIVO_SQL = RAIZ / "sql" / "02_consultas_negocio.sql"
OUTPUTS = RAIZ / "outputs"


def separar_consultas(texto: str) -> dict[str, str]:
    """Quebra o arquivo .sql em {nome: sql} usando a linha '-- @consulta: nome'."""
    partes = re.split(r"^-- @consulta:\s*(\w+)\s*$", texto, flags=re.MULTILINE)
    # partes = [cabeçalho, nome1, sql1, nome2, sql2, ...]
    return {partes[i]: partes[i + 1].strip() for i in range(1, len(partes), 2)}


def carregar_consultas() -> dict[str, str]:
    return separar_consultas(ARQUIVO_SQL.read_text(encoding="utf-8"))
