"""Materializa o schema marts a partir do schema refined."""

import sys

from pipeline.db import conectar, criar_schema

TABELAS_REFINADAS = (
    ("refined", "tb_gastos"),
    ("refined", "tb_paises"),
)

TABELA_GASTOS = {
    "ano": "INTEGER",
    "id_pais": "INTEGER",
    "gasto_usd": "DECIMAL(10, 2)",
    "expectativa_de_vida": "DECIMAL(3, 1)",
}
TABELA_PAISES = {
    "id_pais": "INTEGER",
    "pais": "VARCHAR",
}


class ErroMart(Exception):
    """Erro de dados que impede a materialização do marts."""


def _tabela_existe(con, schema, tabela):
    return (
        con.execute(
            """
            SELECT count(*)
            FROM information_schema.tables
            WHERE table_schema = ? AND table_name = ?
            """,
            [schema, tabela],
        ).fetchone()[0]
        > 0
    )


def _colunas_tipo(con, tabela):
    return {nome: tipo for nome, tipo, *_ in con.execute(f"DESCRIBE {tabela}").fetchall()}


def _validar_tabelas_refined(con):
    for schema, tabela in TABELAS_REFINADAS:
        if not _tabela_existe(con, schema, tabela):
            print(
                f"Tabela {schema}.{tabela} não encontrada. "
                'Rode "uv run python -m pipeline.transformacao".'
            )
            raise SystemExit(1)


def _normalizar_tipo(tipo):
    return tipo.upper().replace(" ", "")


def _validar_colunas_refined(con):
    colunas_gastos = _colunas_tipo(con, "refined.tb_gastos")
    for nome, tipo in TABELA_GASTOS.items():
        if nome not in colunas_gastos:
            raise ErroMart(f"Coluna obrigatória ausente em refined.tb_gastos: {nome}.")
        if _normalizar_tipo(colunas_gastos[nome]) != _normalizar_tipo(tipo):
            raise ErroMart(
                f"Tipo incompatível em refined.tb_gastos.{nome}: "
                f"esperado {tipo}, encontrado {colunas_gastos[nome]}."
            )

    colunas_paises = _colunas_tipo(con, "refined.tb_paises")
    for nome, tipo in TABELA_PAISES.items():
        if nome not in colunas_paises:
            raise ErroMart(f"Coluna obrigatória ausente em refined.tb_paises: {nome}.")
        if _normalizar_tipo(colunas_paises[nome]) != _normalizar_tipo(tipo):
            raise ErroMart(
                f"Tipo incompatível em refined.tb_paises.{nome}: "
                f"esperado {tipo}, encontrado {colunas_paises[nome]}."
            )


def _validar_nulos_obrigatorios(con):
    nulos = {
        "refined.tb_gastos.ano": con.execute(
            "SELECT count(*) FROM refined.tb_gastos WHERE ano IS NULL"
        ).fetchone()[0],
        "refined.tb_gastos.id_pais": con.execute(
            "SELECT count(*) FROM refined.tb_gastos WHERE id_pais IS NULL"
        ).fetchone()[0],
        "refined.tb_paises.id_pais": con.execute(
            "SELECT count(*) FROM refined.tb_paises WHERE id_pais IS NULL"
        ).fetchone()[0],
    }
    for coluna, quantidade in nulos.items():
        if quantidade:
            raise ErroMart(
                f"Tabela {coluna.rsplit('.', 1)[0]}, coluna {coluna.rsplit('.', 1)[1]}, "
                f"{quantidade} registros afetados."
            )


def _verificar_conflitos_fato(con):
    chaves = con.execute(
        """
        WITH detalhes AS (
            SELECT
                ano,
                id_pais,
                count(*) AS ocorrencias,
                count(DISTINCT cast(gasto_usd AS VARCHAR)) AS gasto_distintos,
                count(DISTINCT cast(expectativa_de_vida AS VARCHAR)) AS expectativa_distintas
            FROM refined.tb_gastos
            GROUP BY ano, id_pais
            HAVING count(*) > 1
        )
        SELECT ano, id_pais, ocorrencias, gasto_distintos, expectativa_distintas
        FROM detalhes
        WHERE gasto_distintos > 1 OR expectativa_distintas > 1
        ORDER BY ano, id_pais
        LIMIT 10
        """
    ).fetchall()
    if not chaves:
        return

    conflito = chaves[0]
    linhas = con.execute(
        """
        SELECT ano, id_pais, gasto_usd, expectativa_de_vida
        FROM refined.tb_gastos
        WHERE ano = ? AND id_pais = ?
        ORDER BY ano, id_pais, gasto_usd NULLS FIRST, expectativa_de_vida NULLS FIRST
        """,
        [conflito[0], conflito[1]],
    ).fetchall()
    raise ErroMart(
        "Chave conflitante em refined.tb_gastos: "
        f"(ano={conflito[0]}, id_pais={conflito[1]}). "
        f"Linhas conflitantes: {linhas}."
    )


def _verificar_unicidade_dimensoes(con):
    duplicatas_paises = con.execute(
        """
        SELECT pais, count(*)
        FROM refined.tb_paises
        WHERE pais IS NOT NULL
        GROUP BY pais
        HAVING count(*) > 1
        """
    ).fetchone()
    if duplicatas_paises is not None:
        raise ErroMart(
            "Dimension country has duplicate business keys: "
            f"pais={duplicatas_paises[0]!r} count={duplicatas_paises[1]}."
        )


def _validar_mart_unicidade(con):
    duplicatas_calendario = con.execute(
        """
        SELECT ano, count(*)
        FROM marts.d_calendario
        GROUP BY ano
        HAVING count(*) > 1
        """
    ).fetchone()
    if duplicatas_calendario is not None:
        raise ErroMart(
            "Dimension calendar has duplicate business keys: "
            f"ano={duplicatas_calendario[0]} count={duplicatas_calendario[1]}."
        )

    duplicatas_paises = con.execute(
        """
        SELECT pais, count(*)
        FROM marts.d_pais
        GROUP BY pais
        HAVING count(*) > 1
        """
    ).fetchone()
    if duplicatas_paises is not None:
        raise ErroMart(
            "Dimension country has duplicate business keys: "
            f"pais={duplicatas_paises[0]!r} count={duplicatas_paises[1]}."
        )

    chaves_fato = con.execute(
        """
        SELECT id_calendario, id_pais, count(*)
        FROM marts.fato_gastos
        GROUP BY id_calendario, id_pais
        HAVING count(*) > 1
        """
    ).fetchone()
    if chaves_fato is not None:
        raise ErroMart(
            "Tabela marts.fato_gastos possui chaves duplicadas: "
            f"id_calendario={chaves_fato[0]}, id_pais={chaves_fato[1]}, ocorrencias={chaves_fato[2]}."
        )


def _remover_duplicatas_fato(con):
    total_geral = con.execute("SELECT count(*) FROM refined.tb_gastos").fetchone()[0]
    total_distinto = con.execute(
        "SELECT count(*) FROM (SELECT DISTINCT ano, id_pais, gasto_usd, expectativa_de_vida FROM refined.tb_gastos)"
    ).fetchone()[0]
    return total_geral - total_distinto


def _construir_mart(con):
    criar_schema(con, "marts")
    con.execute(
        """
        CREATE OR REPLACE TABLE marts.d_calendario AS
        WITH anos AS (
            SELECT DISTINCT ano
            FROM refined.tb_gastos
            WHERE ano IS NOT NULL
            ORDER BY ano
        )
        SELECT
            cast(row_number() OVER (ORDER BY ano) AS INTEGER) AS id_calendario,
            cast(ano AS INTEGER) AS ano
        FROM anos
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE marts.d_pais AS
        SELECT cast(id_pais AS INTEGER) AS id_pais, cast(pais AS VARCHAR) AS pais
        FROM refined.tb_paises
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE marts.fato_gastos AS
        WITH fato_base AS (
            SELECT
                cast(d.id_calendario AS INTEGER) AS id_calendario,
                cast(g.id_pais AS INTEGER) AS id_pais,
                cast(g.gasto_usd AS DECIMAL(10, 2)) AS gasto_usd,
                cast(g.expectativa_de_vida AS DECIMAL(3, 1)) AS expectativa_de_vida
            FROM refined.tb_gastos AS g
            JOIN marts.d_calendario AS d ON d.ano = g.ano
        )
        SELECT DISTINCT *
        FROM fato_base
        """
    )


def _validar_integridade_referencial(con):
    invalidas = con.execute(
        """
        SELECT g.ano, g.id_pais
        FROM refined.tb_gastos AS g
        LEFT JOIN marts.d_calendario AS d ON d.ano = g.ano
        WHERE g.ano IS NOT NULL AND d.id_calendario IS NULL
        LIMIT 10
        """
    ).fetchall()
    if invalidas:
        ano, id_pais = invalidas[0]
        raise ErroMart(
            "Integridade referencial inválida em marts.fato_gastos: "
            f"ano={ano}, id_pais={id_pais} não existe em marts.d_calendario."
        )

    invalidas_pais = con.execute(
        """
        SELECT g.ano, g.id_pais
        FROM refined.tb_gastos AS g
        LEFT JOIN marts.d_pais AS p ON p.id_pais = g.id_pais
        WHERE g.id_pais IS NOT NULL AND p.id_pais IS NULL
        LIMIT 10
        """
    ).fetchall()
    if invalidas_pais:
        ano, id_pais = invalidas_pais[0]
        raise ErroMart(
            "Integridade referencial inválida em marts.fato_gastos: "
            f"ano={ano}, id_pais={id_pais} não existe em marts.d_pais."
        )


def _contagem(con, consulta):
    return con.execute(consulta).fetchone()[0]


def _formatar_numero(numero):
    return f"{numero:,}".replace(",", ".")


def _imprimir_resultados(con):
    calendario = _contagem(con, "SELECT count(*) FROM marts.d_calendario")
    paises = _contagem(con, "SELECT count(*) FROM marts.d_pais")
    fato = _contagem(con, "SELECT count(*) FROM marts.fato_gastos")
    duplicatas_calendario = _contagem(
        con, "SELECT count(*) FROM (SELECT ano FROM marts.d_calendario GROUP BY ano HAVING count(*) > 1)"
    )
    duplicatas_paises = _contagem(
        con, "SELECT count(*) FROM (SELECT pais FROM marts.d_pais GROUP BY pais HAVING count(*) > 1)"
    )
    duplicatas_removidas = _remover_duplicatas_fato(con)

    print(
        f"{'marts.d_calendario':<25}{_formatar_numero(calendario)} -> "
        f"{_formatar_numero(calendario)} linhas ({_formatar_numero(duplicatas_calendario)} duplicatas)"
    )
    nulos_calendario = con.execute(
        "SELECT count(*) FILTER (WHERE ano IS NULL) FROM marts.d_calendario"
    ).fetchone()
    print(
        "    nulos mantidos: "
        + ", ".join(
            f"{coluna} {_formatar_numero(quantidade)}"
            for coluna, quantidade in zip(("ano",), nulos_calendario)
        )
    )

    print(
        f"{'marts.d_pais':<25}{_formatar_numero(paises)} -> "
        f"{_formatar_numero(paises)} linhas ({_formatar_numero(duplicatas_paises)} duplicatas)"
    )
    nulos_paises = con.execute(
        "SELECT count(*) FILTER (WHERE pais IS NULL) FROM marts.d_pais"
    ).fetchone()[0]
    print(f"    nulos mantidos: pais {_formatar_numero(nulos_paises)}")

    print(
        f"{'marts.fato_gastos':<25}{_formatar_numero(fato)} -> "
        f"{_formatar_numero(fato)} linhas ({_formatar_numero(duplicatas_removidas)} duplicatas)"
    )
    nulos_fato = con.execute(
        """
        SELECT
            count(*) FILTER (WHERE gasto_usd IS NULL),
            count(*) FILTER (WHERE expectativa_de_vida IS NULL)
        FROM marts.fato_gastos
        """
    ).fetchone()
    print(
        "    nulos mantidos: "
        + ", ".join(
            f"{coluna} {_formatar_numero(quantidade)}"
            for coluna, quantidade in zip(("gasto_usd", "expectativa_de_vida"), nulos_fato)
        )
    )

    print(f"Anos distintos: {_formatar_numero(_contagem(con, 'SELECT count(DISTINCT ano) FROM refined.tb_gastos'))}")
    print(f"Países distintos: {_formatar_numero(_contagem(con, 'SELECT count(DISTINCT id_pais) FROM refined.tb_paises'))}")
    print(f"Registros na tabela fato: {_formatar_numero(fato)}")
    print(f"Duplicatas removidas: {_formatar_numero(_remover_duplicatas_fato(con))}")
    print(f"Registros rejeitados por inconsistência: {_formatar_numero(0)}")
    total = calendario + paises + fato
    print(f"TOTAL: 3 tabelas materializadas, {_formatar_numero(total)} registros.")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    con = conectar()
    try:
        _validar_tabelas_refined(con)
        try:
            _validar_colunas_refined(con)
            _validar_nulos_obrigatorios(con)
            _verificar_unicidade_dimensoes(con)
            _verificar_conflitos_fato(con)
            _construir_mart(con)
            _validar_mart_unicidade(con)
            _validar_integridade_referencial(con)
        except ErroMart as erro:
            print(erro)
            sys.exit(1)
        _imprimir_resultados(con)
    finally:
        con.close()


if __name__ == "__main__":
    main()
