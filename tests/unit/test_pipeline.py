import io
from pathlib import Path
from urllib.error import URLError

import duckdb
import pandas as pd
import pytest

from pipeline import db, ingestao, marts, transformacao


class SaidaTeste(io.StringIO):
    def reconfigure(self, **kwargs):
        pass


@pytest.fixture
def conexao():
    banco = duckdb.connect(":memory:")
    yield banco
    banco.close()


def criar_refined_valido(con):
    con.execute("CREATE SCHEMA refined")
    con.execute(
        """
        CREATE TABLE refined.tb_paises (
            id_pais INTEGER,
            pais VARCHAR
        )
        """
    )
    con.execute("INSERT INTO refined.tb_paises VALUES (1, 'Alpha'), (2, 'Beta')")
    con.execute(
        """
        CREATE TABLE refined.tb_gastos (
            ano INTEGER,
            id_pais INTEGER,
            gasto_usd DECIMAL(10, 2),
            expectativa_de_vida DECIMAL(3, 1)
        )
        """
    )
    con.execute(
        """
        INSERT INTO refined.tb_gastos VALUES
            (2000, 1, 100, 60),
            (2001, 1, 120, 61),
            (2000, 2, 300, 70)
        """
    )


def criar_raw_valido(con):
    con.execute("CREATE SCHEMA raw")
    con.execute(
        """
        CREATE TABLE raw.gastos (
            "Year" VARCHAR,
            "Country" VARCHAR,
            "Spending_USD" VARCHAR,
            "Life_Expectancy" VARCHAR
        )
        """
    )
    con.execute(
        """
        INSERT INTO raw.gastos VALUES
            ('2000', 'Alpha', '100', '60.0'),
            ('2001', 'Alpha', '120', '61.0'),
            ('2000', 'Beta', '300', '70.0')
        """
    )


def test_conectar_usa_banco_do_projeto(monkeypatch):
    chamada = {}
    conexao_fake = object()

    def conectar_falso(caminho):
        chamada["caminho"] = caminho
        return conexao_fake

    monkeypatch.setattr(db._duckdb, "connect", conectar_falso)

    assert db.conectar() is conexao_fake
    assert chamada["caminho"] == str(
        Path(db.__file__).resolve().parent.parent / "expectativa_de_vida.duckdb"
    )


def test_criar_schema_e_gravar_dados(conexao):
    db.criar_schema(conexao, 'camada"teste')
    quantidade = db.gravar(
        conexao,
        pd.DataFrame({"valor": [10, 20]}),
        'camada"teste',
        "registros",
    )

    assert quantidade == 2
    assert conexao.execute(
        'SELECT valor FROM "camada""teste".registros ORDER BY valor'
    ).fetchall() == [(10,), (20,)]
    assert (
        conexao.execute(
            """
        SELECT count(*) FROM duckdb_views()
        WHERE view_name LIKE '__dataframe_%'
        """
        ).fetchone()[0]
        == 0
    )


def test_gravar_remove_view_temporaria_quando_a_tabela_falha(conexao):
    with pytest.raises(duckdb.CatalogException):
        db.gravar(conexao, pd.DataFrame({"valor": [1]}), "inexistente", "tabela")

    assert (
        conexao.execute(
            """
        SELECT count(*) FROM duckdb_views()
        WHERE view_name LIKE '__dataframe_%'
        """
        ).fetchone()[0]
        == 0
    )


def test_ingestao_baixa_csv_e_limpa_arquivo_temporario(tmp_path, monkeypatch):
    monkeypatch.setattr(ingestao, "PASTA_RAW", tmp_path)
    monkeypatch.setattr(ingestao, "urlopen", lambda url: io.BytesIO(b"conteudo"))
    destino = tmp_path / "healthexp.csv"

    ingestao._baixar_arquivo(destino)

    assert destino.read_bytes() == b"conteudo"
    assert list(tmp_path.iterdir()) == [destino]


def test_ingestao_reporta_erro_de_download_e_limpa_temporario(tmp_path, monkeypatch):
    monkeypatch.setattr(ingestao, "PASTA_RAW", tmp_path)

    def falhar_download(url):
        raise URLError("sem conexão")

    monkeypatch.setattr(ingestao, "urlopen", falhar_download)

    with pytest.raises(SystemExit, match="1"):
        ingestao._baixar_arquivo(tmp_path / "healthexp.csv")

    assert list(tmp_path.iterdir()) == []


def test_ingestao_main_baixa_csv_quando_arquivo_nao_existe(tmp_path, monkeypatch):
    pasta_raw = tmp_path / "raw"
    caminho_banco = tmp_path / "ingestao.duckdb"
    monkeypatch.setattr(ingestao, "PASTA_RAW", pasta_raw)

    def baixar(arquivo):
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(
            "Year,Country,Spending_USD,Life_Expectancy\n2000,Alpha,100,60.0\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(ingestao, "_baixar_arquivo", baixar)
    monkeypatch.setattr(
        ingestao, "conectar", lambda: duckdb.connect(str(caminho_banco))
    )
    monkeypatch.setattr("sys.stdout", SaidaTeste())

    ingestao.main()

    con = duckdb.connect(str(caminho_banco), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM raw.gastos").fetchone() == (1,)
    finally:
        con.close()


def test_pipeline_completo_materializa_as_tres_camadas(tmp_path, monkeypatch):
    pasta_raw = tmp_path / "raw"
    pasta_raw.mkdir()
    (pasta_raw / "healthexp.csv").write_text(
        "Year,Country,Spending_USD,Life_Expectancy\n"
        "2000,Alpha,100,60.0\n"
        "2001,Alpha,120,61.0\n"
        "2000,Beta,300,70.0\n"
        "2001,Beta,340,71.0\n"
        "2000,Alpha,100,60.0\n",
        encoding="utf-8",
    )
    caminho_banco = tmp_path / "pipeline.duckdb"
    monkeypatch.setattr(ingestao, "PASTA_RAW", pasta_raw)
    monkeypatch.setattr(
        ingestao,
        "_baixar_arquivo",
        lambda arquivo: pytest.fail("não deveria baixar um CSV já existente"),
    )
    for modulo in (ingestao, transformacao, marts):
        monkeypatch.setattr(
            modulo, "conectar", lambda: duckdb.connect(str(caminho_banco))
        )
    saida = SaidaTeste()
    monkeypatch.setattr("sys.stdout", saida)

    ingestao.main()
    transformacao.main()
    marts.main()

    con = duckdb.connect(str(caminho_banco), read_only=True)
    try:
        contagens = con.execute(
            """
            SELECT
                (SELECT count(*) FROM raw.gastos),
                (SELECT count(*) FROM refined.tb_paises),
                (SELECT count(*) FROM refined.tb_gastos),
                (SELECT count(*) FROM marts.d_calendario),
                (SELECT count(*) FROM marts.d_pais),
                (SELECT count(*) FROM marts.fato_gastos)
            """
        ).fetchone()
        linhas_fato = con.execute(
            """
            SELECT d.ano, p.pais, f.gasto_usd, f.expectativa_de_vida
            FROM marts.fato_gastos AS f
            JOIN marts.d_calendario AS d USING (id_calendario)
            JOIN marts.d_pais AS p USING (id_pais)
            ORDER BY d.ano, p.pais
            """
        ).fetchall()
    finally:
        con.close()

    assert contagens == (5, 2, 4, 2, 2, 4)
    assert linhas_fato == [
        (2000, "Alpha", 100, 60),
        (2000, "Beta", 300, 70),
        (2001, "Alpha", 120, 61),
        (2001, "Beta", 340, 71),
    ]
    assert "TOTAL: 3 tabelas materializadas" in saida.getvalue()


def test_transformacao_detecta_tabela_raw_ausente(conexao):
    assert transformacao._tabela_raw_existe(conexao) is False


def test_transformacao_main_para_quando_raw_nao_existe(monkeypatch):
    conexao = duckdb.connect(":memory:")
    monkeypatch.setattr(transformacao, "conectar", lambda: conexao)
    monkeypatch.setattr("sys.stdout", SaidaTeste())

    with pytest.raises(SystemExit, match="1"):
        transformacao.main()

    with pytest.raises(duckdb.ConnectionException, match="already closed"):
        conexao.execute("SELECT 1")


def test_transformacao_detecta_colunas_inesperadas(conexao):
    conexao.execute("CREATE SCHEMA raw")
    conexao.execute("CREATE TABLE raw.gastos (Year VARCHAR, coluna_extra VARCHAR)")

    with pytest.raises(transformacao.ErroTransformacao, match="Colunas inesperadas"):
        transformacao._validar_colunas(conexao)


def test_transformacao_valida_conversoes_e_preserva_nulos(conexao):
    criar_raw_valido(conexao)
    conexao.execute(
        """
        INSERT INTO raw.gastos VALUES
            ('2002', NULL, NULL, NULL)
        """
    )

    transformacao._validar_colunas(conexao)
    transformacao._validar_conversoes(conexao)
    transformacao._criar_tabelas_temporarias(conexao)
    transformacao._verificar_conflitos(conexao)

    assert (
        conexao.execute(
            "SELECT count(*) FROM gastos_convertidos WHERE pais IS NULL"
        ).fetchone()[0]
        == 1
    )
    assert transformacao._primeiro_valor_invalido(conexao, "Year", "INTEGER") is None


def test_transformacao_detecta_valor_numerico_invalido(conexao):
    criar_raw_valido(conexao)
    conexao.execute(
        """
        INSERT INTO raw.gastos VALUES ('2002', 'Alpha', 'inválido', '62.0')
        """
    )

    with pytest.raises(
        transformacao.ErroTransformacao,
        match="raw.gastos.Spending_USD",
    ):
        transformacao._validar_conversoes(conexao)


def test_transformacao_main_faz_rollback_quando_conversao_falha(monkeypatch):
    conexao = duckdb.connect(":memory:")
    criar_raw_valido(conexao)
    conexao.execute(
        "INSERT INTO raw.gastos VALUES ('2002', 'Alpha', 'inválido', '62.0')"
    )
    monkeypatch.setattr(transformacao, "conectar", lambda: conexao)
    monkeypatch.setattr("sys.stdout", SaidaTeste())

    with pytest.raises(SystemExit, match="1"):
        transformacao.main()

    with pytest.raises(duckdb.ConnectionException, match="already closed"):
        conexao.execute("SELECT 1")


def test_transformacao_detecta_conflito_de_chave(conexao):
    criar_raw_valido(conexao)
    conexao.execute("INSERT INTO raw.gastos VALUES ('2000', 'Alpha', '999', '60.0')")
    transformacao._criar_tabelas_temporarias(conexao)

    with pytest.raises(
        transformacao.ErroTransformacao,
        match=r"\(ano=2000, id_pais=1\)",
    ):
        transformacao._verificar_conflitos(conexao)

    assert transformacao._formatar_valor(None) == "NULL"
    assert transformacao._formatar_chave(None, 1) == "(ano=NULL, id_pais=1)"


def test_marts_validam_tabelas_e_tipos_refined(conexao):
    with pytest.raises(SystemExit, match="1"):
        marts._validar_tabelas_refined(conexao)

    criar_refined_valido(conexao)
    marts._validar_tabelas_refined(conexao)
    marts._validar_colunas_refined(conexao)
    assert marts._normalizar_tipo("decimal (10, 2)") == "DECIMAL(10,2)"


@pytest.mark.parametrize(
    ("ddl", "mensagem"),
    [
        (
            "CREATE TABLE refined.tb_paises (id_pais INTEGER)",
            "Coluna obrigatória ausente em refined.tb_paises",
        ),
        (
            "CREATE TABLE refined.tb_paises (id_pais VARCHAR, pais VARCHAR)",
            "Tipo incompatível em refined.tb_paises.id_pais",
        ),
    ],
)
def test_marts_rejeitam_estrutura_invalida_de_paises(conexao, ddl, mensagem):
    conexao.execute("CREATE SCHEMA refined")
    conexao.execute(
        """
        CREATE TABLE refined.tb_gastos (
            ano INTEGER,
            id_pais INTEGER,
            gasto_usd DECIMAL(10, 2),
            expectativa_de_vida DECIMAL(3, 1)
        )
        """
    )
    conexao.execute(ddl)

    with pytest.raises(marts.ErroMart, match=mensagem):
        marts._validar_colunas_refined(conexao)


@pytest.mark.parametrize(
    ("tabela", "ddl", "mensagem"),
    [
        (
            "tb_gastos",
            "CREATE TABLE refined.tb_gastos (ano INTEGER)",
            "Coluna obrigatória ausente",
        ),
        (
            "tb_gastos",
            """
            CREATE TABLE refined.tb_gastos (
                ano INTEGER, id_pais INTEGER, gasto_usd VARCHAR,
                expectativa_de_vida DECIMAL(3,1)
            )
            """,
            "Tipo incompatível",
        ),
    ],
)
def test_marts_rejeitam_estrutura_refined_invalida(conexao, tabela, ddl, mensagem):
    conexao.execute("CREATE SCHEMA refined")
    conexao.execute(ddl)
    if tabela == "tb_gastos" and "id_pais INTEGER, pais VARCHAR" not in ddl:
        conexao.execute(
            "CREATE TABLE refined.tb_paises (id_pais INTEGER, pais VARCHAR)"
        )

    with pytest.raises(marts.ErroMart, match=mensagem):
        marts._validar_colunas_refined(conexao)


def test_marts_detectam_nulos_obrigatorios(conexao):
    criar_refined_valido(conexao)
    conexao.execute("INSERT INTO refined.tb_gastos VALUES (NULL, 1, 10, 50)")

    with pytest.raises(marts.ErroMart, match="refined.tb_gastos"):
        marts._validar_nulos_obrigatorios(conexao)


def test_marts_main_reporta_erro_de_validacao(monkeypatch):
    conexao = duckdb.connect(":memory:")
    criar_refined_valido(conexao)
    conexao.execute("INSERT INTO refined.tb_gastos VALUES (NULL, 1, 10, 50)")
    monkeypatch.setattr(marts, "conectar", lambda: conexao)
    monkeypatch.setattr("sys.stdout", SaidaTeste())

    with pytest.raises(SystemExit, match="1"):
        marts.main()

    with pytest.raises(duckdb.ConnectionException, match="already closed"):
        conexao.execute("SELECT 1")


def test_marts_detectam_chave_de_fato_conflitante(conexao):
    criar_refined_valido(conexao)
    conexao.execute("INSERT INTO refined.tb_gastos VALUES (2000, 1, 999, 60)")

    with pytest.raises(marts.ErroMart, match="Chave conflitante"):
        marts._verificar_conflitos_fato(conexao)


def test_marts_detectam_pais_duplicado_em_refined(conexao):
    criar_refined_valido(conexao)
    conexao.execute("INSERT INTO refined.tb_paises VALUES (3, 'Alpha')")

    with pytest.raises(marts.ErroMart, match="duplicate business keys"):
        marts._verificar_unicidade_dimensoes(conexao)


@pytest.mark.parametrize(
    ("ddl", "mensagem"),
    [
        (
            "INSERT INTO marts.d_calendario VALUES (2, 2000)",
            "Dimension calendar has duplicate",
        ),
        (
            "INSERT INTO marts.d_pais VALUES (3, 'Alpha')",
            "Dimension country has duplicate",
        ),
        (
            "INSERT INTO marts.fato_gastos VALUES (1, 1, 999, 60)",
            "chaves duplicadas",
        ),
    ],
)
def test_marts_detectam_duplicatas_nas_tabelas_mart(conexao, ddl, mensagem):
    criar_refined_valido(conexao)
    marts._construir_mart(conexao)
    conexao.execute(ddl)

    with pytest.raises(marts.ErroMart, match=mensagem):
        marts._validar_mart_unicidade(conexao)


def test_marts_detectam_referencia_a_ano_ausente(conexao):
    criar_refined_valido(conexao)
    marts._construir_mart(conexao)
    conexao.execute("INSERT INTO refined.tb_gastos VALUES (2099, 1, 50, 50)")

    with pytest.raises(marts.ErroMart, match="não existe em marts.d_calendario"):
        marts._validar_integridade_referencial(conexao)


def test_marts_detectam_referencia_a_pais_ausente(conexao):
    criar_refined_valido(conexao)
    marts._construir_mart(conexao)
    conexao.execute("INSERT INTO refined.tb_gastos VALUES (2000, 99, 50, 50)")
    conexao.execute("DELETE FROM marts.d_pais WHERE id_pais = 2")

    with pytest.raises(marts.ErroMart, match="não existe em marts.d_pais"):
        marts._validar_integridade_referencial(conexao)


def test_marts_constroem_tabelas_e_contam_duplicatas(conexao):
    criar_refined_valido(conexao)
    conexao.execute("INSERT INTO refined.tb_gastos VALUES (2000, 1, 100, 60)")
    marts._construir_mart(conexao)

    assert marts._remover_duplicatas_fato(conexao) == 1
    marts._validar_mart_unicidade(conexao)
    marts._validar_integridade_referencial(conexao)
    marts._imprimir_resultados(conexao)


def test_formatador_de_contagens_com_separador_de_milhar():
    assert transformacao._formatar_numero(1234567) == "1.234.567"
    assert marts._formatar_numero(1234567) == "1.234.567"
