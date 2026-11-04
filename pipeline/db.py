"""Camada comum de acesso ao DuckDB, limitada a conexão, schema e gravação.

Os caminhos são relativos a este módulo, não ao diretório de execução, para
que scripts iniciados de outras pastas sempre usem o banco do projeto.
Importar o módulo não abre nem cria o banco, evitando efeitos colaterais nas
etapas que apenas precisam reutilizar estas funções.
Este módulo não lê arquivos, escolhe tabelas nem altera tipos ou valores:
essas decisões pertencem a cada etapa do curso e não devem ficar escondidas
em uma regra compartilhada.
A tabela é substituída a cada gravação e a contagem retornada é consultada no
banco, para refletir exatamente o conteúdo persistido sem deixar relações
temporárias para trás.
Quem chama conectar() é responsável por fechar a conexão.
"""

from pathlib import Path as _Path
from uuid import uuid4 as _uuid4

import duckdb as _duckdb

PASTA_RAW = _Path(__file__).resolve().parent.parent / "raw"


def conectar():
    return _duckdb.connect(
        str(_Path(__file__).resolve().parent.parent / "expectativa_de_vida.duckdb")
    )


def criar_schema(con, nome):
    schema = '"' + nome.replace('"', '""') + '"'
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")


def gravar(con, df, schema, tabela):
    nome_view = f"__dataframe_{_uuid4().hex}"
    identificador_schema = '"' + schema.replace('"', '""') + '"'
    identificador_tabela = '"' + tabela.replace('"', '""') + '"'
    identificador_view = '"' + nome_view + '"'

    con.register(nome_view, df)
    try:
        con.execute(
            f"CREATE OR REPLACE TABLE {identificador_schema}.{identificador_tabela} "
            f"AS SELECT * FROM {identificador_view}"
        )
        return con.execute(
            f"SELECT count(*) FROM {identificador_schema}.{identificador_tabela}"
        ).fetchall()[0][0]
    finally:
        con.unregister(nome_view)
