CONTEXTO
Estou construindo um pipeline de dados em Python sobre o dataset público de Expectativa de vida versus gastos com saúde do site https://www.timestored.com/data/sample/healthexp.csv. Trabalho com spec-driven development:
a spec abaixo é a fonte da verdade e o código é consequência dela. Não
acrescente requisito que não esteja escrito aqui. Se algo estiver ambíguo,
pergunte antes de escrever código.

STACK
- Python 3.13, uv, DuckDB (expectativa_de_vida.duckdb na raiz do projeto)
- streamlit e plotly (plotly.express), já instalados com uv add

O QUE JÁ EXISTE (use, não reimplemente)
O schema marts, com 3 tabelas, criado por pipeline/marts.py:
d_calendario, d_pais, fato_gastos
As consultas em SQL/marts, que calculam os seis indicadores e os cinco gráficos.
Quero 6 cartões na ordem dos SQLs 01 a 06 e gráficos de 07 a 11.

ARTEFATOS A PRODUZIR
painel.py, na raiz: leitura, formatação e gráficos. Não importa streamlit.
app.py, na raiz: a página. Executável com:
  uv run streamlit run app.py

SPEC
1. LEITURA (painel.py)
   ler(SQL/marts, ano_inicio, ano_fim, pais) -> dict nome -> DataFrame.
   Executa cada consulta SQL existente em SQL/marts com os parâmetros de
   período e país. Não calcular indicadores em Python.
   Conexão com duckdb.connect("expectativa_de_vida.duckdb", read_only=True), aberta e
   fechada dentro de ler(). Motivo: conexão aberta segura o arquivo, e o
   pipeline.marts não consegue gravar com o painel de pé.

2. NENHUM CÁLCULO
   Proibido em painel.py e app.py: groupby, sum, mean, count, merge, pivot,
   e qualquer conta entre colunas. Permitido: ordenar, filtrar linhas,
   head(n), renomear coluna e formatar texto.
   Motivo: número novo na tela exige um .sql novo em marts. Se faltar
   algum número, pare e diga qual mart está faltando.

3. LAYOUT (app.py) — de cima para baixo, layout="wide"
   Cabeçalho: título "Expectativa de vida versus gastos com saúde
· visão analítica" à esquerda; à direita,
     filtro de período com rótulo "Selecione o(s) Ano(s)" e filtro múltiplo
     de País com rótulo "Selecione o(s) país(es)"
   Faixa 1: 6  cartões (st.metric), nesta ordem, cada rótulo com a
     definição curta:
--# 01_Total_Registros.sql (Interger)
--# 02_Total_paises.sql (Interger)
--# 03_Media_gastos_usd.sql (Gasto médio (USD), decimal, 2; sem prefixo no valor)
--# 04_Max_gastos_usd.sql (Maior gasto (USD), decimal, 2; sem prefixo no valor)
--# 05_Min_gastos_usd.sql (Menor gasto (USD), decimal, 2; sem prefixo no valor)
--# 06_Media_anos_expectativa_de_vida.sql (decimal, 2)
   Faixa 2, 3 gráficos:
--# 07_Gastos_pais.sql (título "Gastos por país", top 10, barras
     horizontais, maior em cima, dólar e valor no final de cada barra;
     sem o título "País" no eixo Y e sem valores graduados no eixo X);
--# 08_Paises_com_maiores_expectativas_de_vida.sql (barras horizontal por
     valor, decimal, 2 e valor no final de cada barra; sem o título "País"
     no eixo Y e sem valores graduados no eixo X);
--# 09_Rank_Paises_com_menores_valores_e_maior_expectativas_de_vida.sql
     (tabela, título centralizado "Ranking de países com menores gastos vs maior expectativa de vida");
   Faixa 3, largura inteira:
--# 10_Linha_do_tempo_com_gastos_e_media_da_idade.sql (gráfico de barra por valor em dólar e idade uma linha traçando o grafico);
   os títulos dos gráficos 07, 08 e 10 ficam centralizados no dashboard;
   Faixa 4, largura inteira:
--# 11_Lista_de_Conferencia.sql (Tabela);
   títulos das tabelas 09 e 11 centralizados no dashboard;
   uma cor só, cartões com fundo #545454, títulos e valores centralizados
   horizontalmente em cada cartão,
   eixo com unidade.
   width="stretch" (use_container_width
   está descontinuado).

4. FORMATO (painel.py), funções puras, sem streamlit e sem banco
   DOLAR(valor, casas=2)  -> "USD$ 1.003.862,14"
   INTERGER (valor, casas=0) -> "96.470"
  MEDIAS (VALORS, CASAS=2) "70,55"
   Milhar com ponto, decimal com vírgula, sempre. Não use locale do sistema.
   Motivo: o resultado não pode depender da máquina de quem roda.
   Uma função por gráfico, recebendo o DataFrame e devolvendo a figura
   plotly. Motivo: o relatório HTML reaproveita as mesmas funções.

5. FILTRO DE PERÍODO
   st.select_slider com os ANOS de fato_gastos, padrão de 1970 a 2020, e
   um filtro de seleção múltipla de País. Sem países selecionados, considera
   todos. Os dois filtros se aplicam aos seis cartões e aos cinco gráficos
   por parâmetros nas consultas SQL. Selecionar país nos gráficos 07/08 ou
   ano na linha do tempo 10 filtra os outros gráficos e os cartões. Países
   selecionados nos gráficos 07/08 são unidos; filtros de país do cabeçalho
   e dos gráficos e anos selecionados são combinados por interseção.

6. CACHE E ERRO
   Leitura com st.cache_data. Um botão "Recarregar dados" limpa o cache.
   Sem expectativa_de_vida.duckdb, arquivo SQL necessário ou tabela fonte
   marts: st.error dizendo o que falta e o comando
   "uv run python -m pipeline.marts", e st.stop().

CRITÉRIOS DE ACEITE
- Com filtros em Todos e 1970–2020, os seis cartões mostram: 274 · 6 ·
  2.546.941,15 · 11.859.179,00 · 10.363,00 · 77,91.
- O período abre com 51 anos (1970 a 2020) e com o filtro aberto até as pontas.
- Uma busca por "groupby", ".sum(", ".mean(" e "merge" em painel.py e
  app.py não encontra nada.
- Com o painel de pé, uv run python -m pipeline.marts roda sem erro de lock.

ENTREGA
1. A spec como docstring no topo de painel.py, com o motivo de cada regra.
2. O código, comentado só onde a decisão não é óbvia.
3. Uma lista final do que você assumiu e que não estava na spec.
