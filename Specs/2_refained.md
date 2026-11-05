##SPEC

ARTEFATO
  pipeline/transformacao.py
  Este módulo lê o schema raw e materializa o schema refined, substituindo o nome genérico anterior por um script específico da transformação.

1. ESCOPO
   Lê de raw, escreve no schema refined. Nunca escreve em raw.
   Entram uma tabela de dados brutos: gastos.
   Para respeitar a Terceira Forma Normal (3FN), a tabela original é normalizada 
   e dividida em duas tabelas no schema refined:
   - refined.tb_paises: Contém a lista de países únicos mapeados para um identificador sequencial.
     Motivo: Elimina a dependência parcial e a redundância de strings de texto repetidas.
   - refined.tb_gastos: Contém as métricas temporárias ligadas ao ID do país e ao ano.
     Motivo: Garante que os atributos não-chave dependam exclusivamente da chave composta (ano, pais_id).

2. NOMES
   Colunas renomeadas para português, snake_case, com o mapa abaixo, completo e literal.
   Nenhuma coluna fora do mapa; nenhuma descartada.
   Motivo: É o vocabulário que vou digitar de memória nos JOINs da aula 3.

   gastos (Origem em raw)
    expectativa_de_vida_Year.csv            -> ano
    expectativa_de_vida_Country.csv         -> pais
    expectativa_de_vida_Spending_USD.csv    -> gasto_usd
    expectativa_de_vida_Life_Expectancy.csv -> expectativa_de_vida

   Tabelas Finais (Refined 3FN):
   refined.tb_paises:
    id_pais (Gerado automaticamente)
    pais (Varchar contendo o nome do país original)

   refined.tb_gastos:
    ano (Integer)
    id_pais (Integer - FK apontando para refined.tb_paises)
    gasto_usd (Decimal)
    expectativa_de_vida (Decimal)

3. TIPOS
  O campo "ano" vai ser INTEGER
  O campo "pais" vai ser VARCHAR
  O campo "gasto_usd" vai ser um DECIMAL(10,2) e em dólar (USD), o ponto não é virgula.
  O campo "expectativa_de_vida" vai ser um DECIMAL(3,1)

  Para o campo "gasto_usd": Para as colunas numéricas, o caractere ponto (.) deve ser completamente ignorado/removido do texto original, tratando o número resultante estritamente como a parte inteira do dado. O valor final deve ser tipado como DECIMAL(10,2).

    • Campo: "gasto_usd"
    • Tipo Físico no Destino: DECIMAL(10,2)
    • Lógica de Ingestão: "Target = CAST(REPLACE(Spending_USD, '.', '') AS DECIMAL(10,2))"


4. CONVERSÃO QUE FALHA
   Para tudo. Use CAST, que estoura, e nunca TRY_CAST ou errors="coerce", 
   que transformam falha em nulo.
   Ao falhar: diga tabela, coluna e um exemplo do valor que não converteu, e encerre com sys.exit(1).
   Motivo: Um nulo fabricado pela conversão fica indistinguível de um nulo verdadeiro do dado, para sempre.

5. DUPLICATAS
   Chave de cada tabela na refined:
     tb_paises (pais)
     tb_gastos (ano, id_pais)
   Linha inteira repetida: mantém uma, e conta quantas saíram.
   Chave repetida com conteúdo diferente: para, mostra a chave e as linhas conflitantes, sys.exit(1). 
   Não escolhe uma por conta própria.
   Motivo: Escolher em silêncio é decidir sem dizer que decidiu.

6. NULOS
   Nenhuma linha é apagada por ter nulo. Nenhum nulo é preenchido.
   Motivo: O nulo é informação factual vinda diretamente da fonte. refined não corrige fato; 
   quem decide o que fazer com ele é a pergunta que o mart responde.

7. SAÍDA NA TELA
   Uma linha por tabela, no formato:
     refined.paises            6 -> 6 linhas  (0 duplicatas)
   Abaixo dela, indentadas, as colunas com nulo e a contagem:
       nulos mantidos: gasto_usd 0, expectativa_de_vida 0
   As contagens vêm do banco, milhar separado por ponto. Linha final com o total. 
   stdout reconfigurado para utf-8.

REEXECUÇÃO
   CREATE OR REPLACE TABLE, nunca acrescenta. Rodar dez vezes = rodar uma.

ERRO
   Antes de transformar, verifica se a tabela de entrada existe em raw. 
   Faltando: diz para rodar "uv run python -m pipeline.ingestao" e encerra com sys.exit(1).
