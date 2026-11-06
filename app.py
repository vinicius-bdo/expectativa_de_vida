import duckdb
import streamlit as st

from painel import (
    CAMINHO_BANCO,
    DOLAR,
    INTERGER,
    MEDIAS,
    ArquivosSQLAusentesError,
    MartsAusentesError,
    grafico_expectativa_pais,
    grafico_gastos_pais,
    grafico_linha_tempo,
    ler,
)

st.set_page_config(
    page_title="Expectativa de vida versus gastos com saúde",
    layout="wide",
)


@st.cache_data(show_spinner=False)
def carregar_dados(ano_inicio, ano_fim, pais, anos_selecionados=None):
    return ler(
        ano_inicio=ano_inicio,
        ano_fim=ano_fim,
        pais=pais,
        anos=anos_selecionados,
    )


def parar_com_erro(mensagem):
    st.error(
        f"{mensagem} Execute `uv run python -m pipeline.marts` para recriar os marts."
    )
    st.stop()


def recarregar_dados():
    carregar_dados.clear()
    st.session_state["geracao_filtros"] = st.session_state.get("geracao_filtros", 0) + 1


def pontos_selecionados(chave):
    estado = st.session_state.get(chave)
    if estado is None:
        return []
    selecao = estado.get("selection")
    if selecao is None:
        return []
    return selecao.get("points", [])


if not CAMINHO_BANCO.is_file():
    parar_com_erro(f"Banco não encontrado: {CAMINHO_BANCO}.")

st.button("Recarregar dados", on_click=recarregar_dados)

st.markdown(
    """
    <style>
    div[class*="st-key-cartao_indicador_"] {
        background-color: #545454;
        border-radius: 0.6rem;
        padding: 0.8rem;
    }
    div[class*="st-key-cartao_indicador_"] [data-testid="stMetricLabel"] {
        display: flex;
        justify-content: center;
        width: 100%;
    }
    div[class*="st-key-cartao_indicador_"] [data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"] {
        width: 100%;
        text-align: center;
    }
    div[class*="st-key-cartao_indicador_"] [data-testid="stMetricLabel"] p {
        margin: 0;
        text-align: center;
        width: 100%;
    }
    div[class*="st-key-cartao_indicador_"] [data-testid="stMetricValue"] {
        text-align: center;
    }
    div[class*="st-key-cartao_indicador_"] [data-testid="stMetricValue"] p {
        text-align: center;
        width: 100%;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

try:
    dados_base = carregar_dados(1970, 2020, None)
except ArquivosSQLAusentesError as erro:
    parar_com_erro(f"Arquivos SQL ausentes em SQL/marts: {erro}.")
except MartsAusentesError as erro:
    parar_com_erro(f"Tabelas marts ausentes: {erro}.")
except duckdb.Error as erro:
    parar_com_erro(f"Erro ao consultar os marts: {erro}.")

anos = dados_base["10_Linha_do_tempo_com_gastos_e_media_da_idade"]["ano"].tolist()
if not anos:
    parar_com_erro("O mart não contém anos para montar o filtro de período.")

paises = (
    dados_base["11_Lista_de_Conferencia"]["pais"]
    .drop_duplicates()
    .sort_values()
    .tolist()
)

geracao_filtros = st.session_state.get("geracao_filtros", 0)
chave_gastos = f"grafico_gastos_{geracao_filtros}"
chave_expectativa = f"grafico_expectativa_{geracao_filtros}"
chave_tempo = f"grafico_tempo_{geracao_filtros}"

cabecalho, filtro_ano, filtro_pais = st.columns([3, 1, 1])
with cabecalho:
    st.title("Expectativa de vida versus gastos com saúde · visão analítica")
with filtro_ano:
    periodo = st.select_slider(
        "Selecione o(s) Ano(s)",
        options=anos,
        value=(1970, 2020),
        format_func=str,
        key=f"filtro_periodo_{geracao_filtros}",
    )
    st.caption("Período aplicado aos cartões e gráficos.")
with filtro_pais:
    paises_selecionados = st.multiselect(
        "Selecione o(s) país(es)",
        paises,
        default=[],
        placeholder="Todos os países",
        key=f"filtro_pais_{geracao_filtros}",
    )

selecoes_pais = {
    ponto["y"]
    for chave in (chave_gastos, chave_expectativa)
    for ponto in pontos_selecionados(chave)
    if "y" in ponto
}
filtros_pais = [
    set(paises_selecionados) if paises_selecionados else None,
    selecoes_pais if selecoes_pais else None,
]
filtros_pais = [filtro for filtro in filtros_pais if filtro is not None]
paises_filtrados = (
    [pais for pais in paises if all(pais in filtro for filtro in filtros_pais)]
    if filtros_pais
    else None
)
anos_selecionados = list(
    dict.fromkeys(
        ponto["x"] for ponto in pontos_selecionados(chave_tempo) if "x" in ponto
    )
)
try:
    dados = carregar_dados(
        periodo[0],
        periodo[1],
        paises_filtrados,
        anos_selecionados or None,
    )
except ArquivosSQLAusentesError as erro:
    parar_com_erro(f"Arquivos SQL ausentes em SQL/marts: {erro}.")
except MartsAusentesError as erro:
    parar_com_erro(f"Tabelas marts ausentes: {erro}.")
except duckdb.Error as erro:
    parar_com_erro(f"Erro ao consultar os marts: {erro}.")

indicadores = (
    ("01_Total_Registros", "total_registros", "Total de registros", INTERGER),
    ("02_Total_paises", "total_paises", "Países", INTERGER),
    ("03_Media_gastos_usd", "media_gastos_usd", "Gasto médio (USD)", MEDIAS),
    ("04_Max_gastos_usd", "max_gastos_usd", "Maior gasto (USD)", MEDIAS),
    ("05_Min_gastos_usd", "min_gastos_usd", "Menor gasto (USD)", MEDIAS),
    (
        "06_Media_anos_expectativa_de_vida",
        "expectativa_de_vida_media_anos",
        "Expectativa média (anos)",
        MEDIAS,
    ),
)

cartoes = st.columns(6)
for indice, (coluna, (nome, campo, rotulo, formatar)) in enumerate(
    zip(cartoes, indicadores)
):
    valor = dados[nome].iloc[0][campo]
    with coluna, st.container(key=f"cartao_indicador_{indice}"):
        st.metric(rotulo, formatar(valor))

linha_esquerda, linha_direita = st.columns(2)
with linha_esquerda:
    st.markdown(
        '<h3 style="text-align: center;">Gastos por país</h3>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        grafico_gastos_pais(dados["07_Gastos_pais"]),
        width="stretch",
        key=chave_gastos,
        on_select="rerun",
        selection_mode=("points", "box", "lasso"),
    )
with linha_direita:
    st.markdown(
        '<h3 style="text-align: center;">Países com maior expectativa de vida</h3>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        grafico_expectativa_pais(dados["08_Paises_com_maiores_expectativas_de_vida"]),
        width="stretch",
        key=chave_expectativa,
        on_select="rerun",
        selection_mode=("points", "box", "lasso"),
    )

st.markdown(
    '<h3 style="text-align: center;">Ranking de países com menores gastos vs maior expectativa de vida</h3>',
    unsafe_allow_html=True,
)
ranking = dados[
    "09_Rank_Paises_com_menores_valores_e_maior_expectativas_de_vida"
].rename(
    columns={
        "pais": "País",
        "gasto_medio_usd": "Gasto médio (USD)",
        "expectativa_media_anos": "Expectativa média (anos)",
        "rank_maior_expectativa": "Posição",
    }
)
ranking["Gasto médio (USD)"] = ranking["Gasto médio (USD)"].map(DOLAR)
ranking["Expectativa média (anos)"] = ranking["Expectativa média (anos)"].map(MEDIAS)
ranking["Posição"] = ranking["Posição"].map(INTERGER)
st.dataframe(ranking, width="stretch", hide_index=True)

st.markdown(
    '<h3 style="text-align: center;">Linha do tempo · gastos e expectativa de vida</h3>',
    unsafe_allow_html=True,
)
st.plotly_chart(
    grafico_linha_tempo(dados["10_Linha_do_tempo_com_gastos_e_media_da_idade"]),
    width="stretch",
    key=chave_tempo,
    on_select="rerun",
    selection_mode=("points", "box", "lasso"),
)

st.markdown(
    '<h3 style="text-align: center;">Lista de conferência</h3>',
    unsafe_allow_html=True,
)
conferencia = dados["11_Lista_de_Conferencia"].rename(
    columns={
        "ano": "Ano",
        "pais": "País",
        "gasto_usd": "Gastos (USD)",
        "expectativa_de_vida": "Expectativa de vida (anos)",
    }
)
conferencia["Ano"] = conferencia["Ano"].map(INTERGER)
conferencia["Gastos (USD)"] = conferencia["Gastos (USD)"].map(DOLAR)
conferencia["Expectativa de vida (anos)"] = conferencia[
    "Expectativa de vida (anos)"
].map(MEDIAS)
st.dataframe(conferencia, width="stretch", hide_index=True)
