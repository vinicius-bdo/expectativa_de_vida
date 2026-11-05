"""Especificação do painel de expectativa de vida versus gastos com saúde.

Fonte da verdade: specs/4_Painel.md. O projeto usa Python, Streamlit, Plotly e
DuckDB; o schema marts (d_calendario, d_pais, fato_gastos) e as consultas em
SQL/marts já existem e são reutilizados. O painel tem seis cartões, na ordem
das consultas 01 a 06, e visualizações das consultas 07 a 11.

LEITURA: ler() executa cada arquivo SQL de SQL/marts com os filtros de ano e
país e devolve um dict de DataFrames. A conexão ao arquivo DuckDB é read-only
e fecha dentro de ler(), pois mantê-la aberta pode impedir que pipeline.marts
grave no banco enquanto o painel está aberto.

SEM CÁLCULOS: painel.py e app.py não calculam indicadores nem fazem contas
entre colunas. Números novos devem ser definidos por uma consulta SQL, para
que regras de negócio permaneçam nos marts. Ordenação, filtragem de linhas,
renomeação e formatação para apresentação são permitidas.

LAYOUT: app.py usa layout wide. O cabeçalho mostra "Expectativa de vida versus
gastos com saúde · visão analítica" e filtros de Ano e País. Depois vêm seis
cartões, três visuais em uma faixa, uma linha do tempo em largura inteira e
uma tabela de conferência em largura inteira. Os títulos dos gráficos 07, 08
e 10, e os títulos das tabelas 09 e 11 ficam centralizados no painel. O
gráfico 07 é horizontal,
top 10, maior valor em cima, título "Gastos por país" e mostra o valor no fim
de cada barra; o 08 também é horizontal e mostra o valor no fim de cada barra;
ambos ocultam o título do eixo Y ("País") e os valores graduados no eixo X,
mantendo a unidade no título do eixo e os valores finais das barras;
o 09 é uma tabela; o 10 combina barras de gasto com linha de expectativa de
vida. Gráficos usam uma cor, eixos com unidades e width="stretch".

FORMATAÇÃO: DOLAR, INTERGER e MEDIAS são funções sem estado e sem locale do
sistema; usam ponto para milhar e vírgula para decimal, para que o resultado
seja consistente em qualquer máquina. Cada função de gráfico recebe um
DataFrame e devolve uma figura Plotly; assim pode ser reutilizada em relatórios
HTML. Este módulo não importa Streamlit nem abre conexões fora de ler().

FILTROS: o seletor de período oferece os anos de fato_gastos e inicia em
1970–2020. País é seleção múltipla; sem países selecionados, considera todos.
Os filtros de ano e país são parâmetros SQL aplicados aos seis cartões e aos
cinco gráficos, evitando recálculos de negócio em Python. Seleções de país
nos gráficos 07/08 e de ano na linha do tempo 10 filtram os demais gráficos
e cartões. Seleções de países vindas dos dois gráficos são unidas; os países
do cabeçalho e dos gráficos, e os anos selecionados, combinam por interseção.

CARTÕES: os seis cartões têm fundo #545454 e os títulos e indicadores ficam
centralizados para facilitar a leitura.

CACHE E ERROS: app.py usa st.cache_data e o botão "Recarregar dados" limpa o
cache. Se faltar o banco, uma consulta SQL ou uma tabela fonte marts, a página
mostra o erro, informa `uv run python -m pipeline.marts` e para com st.stop().
"""

from decimal import Decimal
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

PASTA_PROJETO = Path(__file__).resolve().parent
PASTA_SQL = PASTA_PROJETO / "SQL" / "marts"
CAMINHO_BANCO = PASTA_PROJETO / "expectativa_de_vida.duckdb"
COR_GRAFICO = "#1F77B4"

ARQUIVOS_SQL = (
    "01_Total_Registros.sql",
    "02_Total_paises.sql",
    "03_Media_gastos_usd.sql",
    "04_Max_gastos_usd.sql",
    "05_Min_gastos_usd.sql",
    "06_Media_anos_expectativa_de_vida.sql",
    "07_Gastos_pais.sql",
    "08_Paises_com_maiores_expectativas_de_vida.sql",
    "09_Rank_Paises_com_menores_valores_e_maior_expectativas_de_vida.sql",
    "10_Linha_do_tempo_com_gastos_e_media_da_idade.sql",
    "11_Lista_de_Conferencia.sql",
)

TABELAS_MARTS = {"d_calendario", "d_pais", "fato_gastos"}


class ArquivosSQLAusentesError(FileNotFoundError):
    """Arquivos de consulta necessários ao painel não encontrados."""


class MartsAusentesError(RuntimeError):
    """Tabelas de origem necessárias às consultas não encontradas."""


def _formatar_decimal(valor, casas):
    if valor is None or pd.isna(valor):
        return "—"
    numero = f"{Decimal(str(valor)):,.{casas}f}"
    return numero.replace(",", "\0").replace(".", ",").replace("\0", ".")


def DOLAR(valor, casas=2):
    return f"USD$ {_formatar_decimal(valor, casas)}"


def INTERGER(valor, casas=0):
    return _formatar_decimal(valor, casas)


def MEDIAS(valor, casas=2):
    return _formatar_decimal(valor, casas)


def ler(pasta_sql=PASTA_SQL, ano_inicio=1970, ano_fim=2020, pais=None, anos=None):
    pasta_sql = Path(pasta_sql)
    ausentes = [nome for nome in ARQUIVOS_SQL if not (pasta_sql / nome).is_file()]
    if ausentes:
        raise ArquivosSQLAusentesError(", ".join(ausentes))

    conexao = duckdb.connect(str(CAMINHO_BANCO), read_only=True)
    try:
        tabelas = {
            linha[0]
            for linha in conexao.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'marts'"
            ).fetchall()
        }
        marts_ausentes = sorted(TABELAS_MARTS - tabelas)
        if marts_ausentes:
            raise MartsAusentesError(", ".join(marts_ausentes))

        parametros = [ano_inicio, ano_fim, anos, anos, pais, pais]
        dados = {}
        for nome in ARQUIVOS_SQL:
            consulta = (pasta_sql / nome).read_text(encoding="utf-8")
            dados[Path(nome).stem] = conexao.execute(
                consulta, parametros
            ).fetchdf()
        return dados
    finally:
        conexao.close()


def grafico_gastos_pais(df):
    dados = df.sort_values("gasto_usd", ascending=True)
    figura = px.bar(
        dados,
        x="gasto_usd",
        y="pais",
        text=dados["gasto_usd"].map(DOLAR),
        orientation="h",
        color_discrete_sequence=[COR_GRAFICO],
        labels={"gasto_usd": "Gastos (USD)", "pais": "País"},
    )
    figura.update_layout(showlegend=False, xaxis_tickprefix="USD$ ", uniformtext_minsize=8)
    figura.update_xaxes(showticklabels=False)
    figura.update_yaxes(title_text="")
    figura.update_traces(
        texttemplate="%{text}",
        textposition="outside",
        cliponaxis=False,
    )
    return figura


def grafico_expectativa_pais(df):
    dados = df.sort_values("expectativa_media_anos", ascending=True)
    figura = px.bar(
        dados,
        x="expectativa_media_anos",
        y="pais",
        text=dados["expectativa_media_anos"].map(MEDIAS),
        orientation="h",
        color_discrete_sequence=[COR_GRAFICO],
        labels={
            "expectativa_media_anos": "Expectativa de vida (anos)",
            "pais": "País",
        },
    )
    figura.update_layout(showlegend=False)
    figura.update_xaxes(showticklabels=False)
    figura.update_yaxes(title_text="")
    figura.update_traces(
        texttemplate="%{text}",
        textposition="outside",
        cliponaxis=False,
    )
    return figura


def grafico_linha_tempo(df):
    figura = make_subplots(specs=[[{"secondary_y": True}]])
    figura.add_trace(
        go.Bar(
            x=df["ano"],
            y=df["gasto_usd"],
            name="Gastos",
            marker_color=COR_GRAFICO,
            hovertemplate="Ano %{x}<br>Gastos USD$ %{y:,.2f}<extra></extra>",
        ),
        secondary_y=False,
    )
    figura.add_trace(
        go.Scatter(
            x=df["ano"],
            y=df["expectativa_media_anos"],
            name="Expectativa média",
            mode="lines+markers",
            line={"color": COR_GRAFICO},
            marker={"color": COR_GRAFICO},
            hovertemplate="Ano %{x}<br>Expectativa %{y:.2f} anos<extra></extra>",
        ),
        secondary_y=True,
    )
    figura.update_layout(showlegend=True)
    figura.update_xaxes(title_text="Ano")
    figura.update_yaxes(
        title_text="Gastos (USD)",
        tickprefix="USD$ ",
        tickformat=",.2f",
        secondary_y=False,
    )
    figura.update_yaxes(
        title_text="Expectativa de vida (anos)",
        tickformat=".2f",
        secondary_y=True,
    )
    return figura
