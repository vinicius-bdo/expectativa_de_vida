"""Normaliza raw.gastos e materializa as tabelas do schema refined."""

import sys

import duckdb

from pipeline.db import conectar, criar_schema

COLUNAS_NUMERICAS = (
    ("Year", "ano", "INTEGER", "tb_gastos"),
    ("Spending_USD", "gasto_usd", "DECIMAL(10, 2)", "tb_gastos"),
    ("Life_Expectancy", "expectativa_de_vida", "DECIMAL(3, 1)", "tb_gastos"),
)
COLUNAS_ORIGEM = ("Year", "Country", "Spending_USD", "Life_Expectancy")


class ErroTransformacao(Exception):
    """Erro de dados que impede a materialização do refined."""


def _tabela_raw_existe(con):
    return (
        con.execute(
            """
        SELECT count(*)
        FROM information_schema.tables
        WHERE table_schema = 'raw' AND table_name = 'gastos'
        """
        ).fetchone()[0]
        > 0
    )


def _validar_colunas(con):
    colunas = tuple(linha[0] for linha in con.execute("DESCRIBE raw.gastos").fetchall())
    if len(colunas) != len(COLUNAS_ORIGEM) or set(colunas) != set(COLUNAS_ORIGEM):
        raise ErroTransformacao(
            "Colunas inesperadas em raw.gastos. "
            f"Esperadas: {', '.join(COLUNAS_ORIGEM)}; "
            f"encontradas: {', '.join(colunas)}."
        )


def _primeiro_valor_invalido(con, coluna, tipo, remover_ponto=False):
    valores = con.execute(
        f'SELECT DISTINCT "{coluna}" FROM raw.gastos WHERE "{coluna}" IS NOT NULL'
    ).fetchall()
    for (valor,) in valores:
        valor_para_converter = (
            valor.replace(".", "") if remover_ponto and valor is not None else valor
        )
        try:
            con.execute(f"SELECT CAST(? AS {tipo})", [valor_para_converter])
        except duckdb.ConversionException:
            return valor
    return None


def _validar_conversoes(con):
    for origem, destino, tipo, tabela_destino in COLUNAS_NUMERICAS:
        valor = _primeiro_valor_invalido(
            con, origem, tipo, remover_ponto=origem == "Spending_USD"
        )
        if valor is not None:
            raise ErroTransformacao(
                f"Falha ao converter raw.gastos.{origem} para "
                f"refined.{tabela_destino}.{destino}; "
                f"exemplo do valor inválido: {valor!r}."
            )


def _criar_tabelas_temporarias(con):
    con.execute(
        """
        CREATE TEMP TABLE gastos_convertidos AS
        SELECT
            CAST("Year" AS INTEGER) AS ano,
            CAST("Country" AS VARCHAR) AS pais,
            CAST(REPLACE("Spending_USD", '.', '') AS DECIMAL(10, 2)) AS gasto_usd,
            CAST("Life_Expectancy" AS DECIMAL(3, 1)) AS expectativa_de_vida
        FROM raw.gastos
        """
    )
    con.execute(
        """
        CREATE TEMP TABLE paises_finais AS
        SELECT
            CAST(row_number() OVER (ORDER BY pais NULLS FIRST) AS INTEGER)
                AS id_pais,
            pais
        FROM (SELECT DISTINCT pais FROM gastos_convertidos)
        """
    )
    con.execute(
        """
        CREATE TEMP TABLE gastos_candidatos AS
        SELECT g.ano, p.id_pais, g.gasto_usd, g.expectativa_de_vida
        FROM gastos_convertidos AS g
        JOIN paises_finais AS p ON g.pais IS NOT DISTINCT FROM p.pais
        """
    )


def _conflitos_gastos(con):
    return con.execute(
        """
        WITH linhas_unicas AS (
            SELECT DISTINCT ano, id_pais, gasto_usd, expectativa_de_vida
            FROM gastos_candidatos
        ),
        chaves_conflitantes AS (
            SELECT ano, id_pais
            FROM linhas_unicas
            GROUP BY ano, id_pais
            HAVING count(*) > 1
        )
        SELECT l.ano, l.id_pais, l.gasto_usd, l.expectativa_de_vida
        FROM linhas_unicas AS l
        JOIN chaves_conflitantes AS c
            ON l.ano IS NOT DISTINCT FROM c.ano
            AND l.id_pais IS NOT DISTINCT FROM c.id_pais
        ORDER BY l.ano NULLS FIRST, l.id_pais, l.gasto_usd NULLS FIRST,
                 l.expectativa_de_vida NULLS FIRST
        """
    ).fetchall()


def _formatar_valor(valor):
    return "NULL" if valor is None else str(valor)


def _formatar_chave(ano, id_pais):
    return f"(ano={_formatar_valor(ano)}, id_pais={_formatar_valor(id_pais)})"


def _verificar_conflitos(con):
    linhas = _conflitos_gastos(con)
    if not linhas:
        return

    mensagens = ["Chaves conflitantes em refined.tb_gastos:"]
    chaves_exibidas = set()
    for ano, id_pais, gasto_usd, expectativa_de_vida in linhas:
        chave = (ano, id_pais)
        if chave not in chaves_exibidas:
            mensagens.append(f"  {_formatar_chave(ano, id_pais)}:")
            chaves_exibidas.add(chave)
        mensagens.append(
            "    "
            f"(gasto_usd={_formatar_valor(gasto_usd)}, "
            "expectativa_de_vida="
            f"{_formatar_valor(expectativa_de_vida)})"
        )
    raise ErroTransformacao("\n".join(mensagens))


def _criar_tabelas_refined(con):
    criar_schema(con, "refined")
    con.execute(
        """
        CREATE OR REPLACE TABLE refined.tb_paises AS
        SELECT id_pais, pais FROM paises_finais
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE refined.tb_gastos AS
        SELECT DISTINCT ano, id_pais, gasto_usd, expectativa_de_vida
        FROM gastos_candidatos
        """
    )


def _contagem(con, consulta):
    return con.execute(consulta).fetchone()[0]


def _formatar_numero(numero):
    return f"{numero:,}".replace(",", ".")


def _imprimir_resultados(con, linhas_paises, linhas_gastos):
    quantidade_paises = _contagem(con, "SELECT count(*) FROM refined.tb_paises")
    quantidade_gastos = _contagem(con, "SELECT count(*) FROM refined.tb_gastos")
    duplicatas_paises = linhas_paises - quantidade_paises
    duplicatas_gastos = linhas_gastos - quantidade_gastos

    nulos_paises = con.execute(
        "SELECT count(*) FILTER (WHERE pais IS NULL) FROM refined.tb_paises"
    ).fetchone()[0]
    nulos_gastos = con.execute(
        """
        SELECT
            count(*) FILTER (WHERE ano IS NULL),
            count(*) FILTER (WHERE id_pais IS NULL),
            count(*) FILTER (WHERE gasto_usd IS NULL),
            count(*) FILTER (WHERE expectativa_de_vida IS NULL)
        FROM refined.tb_gastos
        """
    ).fetchone()

    print(
        f"{'refined.paises':<25}{_formatar_numero(linhas_paises)} -> "
        f"{_formatar_numero(quantidade_paises)} linhas "
        f"({_formatar_numero(duplicatas_paises)} duplicatas)"
    )
    print(f"    nulos mantidos: pais {_formatar_numero(nulos_paises)}")
    print(
        f"{'refined.gastos':<25}{_formatar_numero(linhas_gastos)} -> "
        f"{_formatar_numero(quantidade_gastos)} linhas "
        f"({_formatar_numero(duplicatas_gastos)} duplicatas)"
    )
    colunas = ("ano", "id_pais", "gasto_usd", "expectativa_de_vida")
    nulos_formatados = ", ".join(
        f"{coluna} {_formatar_numero(quantidade)}"
        for coluna, quantidade in zip(colunas, nulos_gastos)
    )
    print(f"    nulos mantidos: {nulos_formatados}")
    total = quantidade_paises + quantidade_gastos
    print(f"Total: {_formatar_numero(total)} linhas")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    con = conectar()
    try:
        if not _tabela_raw_existe(con):
            print(
                "Tabela raw.gastos não encontrada. "
                'Rode "uv run python -m pipeline.ingestao".'
            )
            sys.exit(1)

        try:
            con.execute("BEGIN TRANSACTION")
            _validar_colunas(con)
            _validar_conversoes(con)
            _criar_tabelas_temporarias(con)
            _verificar_conflitos(con)
            linhas_paises = _contagem(con, "SELECT count(*) FROM gastos_convertidos")
            linhas_gastos = _contagem(con, "SELECT count(*) FROM gastos_candidatos")
            _criar_tabelas_refined(con)
            con.execute("COMMIT")
        except ErroTransformacao as erro:
            con.execute("ROLLBACK")
            print(erro)
            sys.exit(1)

        _imprimir_resultados(con, linhas_paises, linhas_gastos)
    finally:
        con.close()


if __name__ == "__main__":
    main()
