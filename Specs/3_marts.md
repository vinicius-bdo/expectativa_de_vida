##SPEC

ARTEFATO
pipeline/marts.py
Este módulo lê o schema refined e materializa o schema marts, implementando o modelo dimensional estrela (Star Schema).
O objetivo é transformar os dados normalizados da camada Refined em um modelo analítico otimizado para consultas, agregações, indicadores e construção de dashboards.
1. ESCOPO
Lê de refined, escreve no schema marts. Nunca escreve em raw ou refined.
Entram duas tabelas de origem:
•	refined.tb_gastos
•	refined.tb_paises
A transformação implementa o modelo dimensional estrela, materializando três tabelas no schema marts:
•	marts.d_calendario: Dimensão temporal contendo os anos disponíveis na base, com atributos que facilitam análises temporais.
•	marts.d_pais: Dimensão geográfica contendo os países, com identificadores e atributos descritivos.
•	marts.fato_gastos: Tabela fato contendo as métricas de gastos e expectativa de vida, relacionadas às dimensões calendário e país.
Modelo dimensional resultante
marts.d_calendario: id_calendario (PK) ano
marts.d_pais: id_pais (PK) pais
marts.fato_gastos: id_calendario (FK -> marts.d_calendario) id_pais (FK -> marts.d_pais) gasto_usd expectativa_de_vida
Granularidade da tabela fato
Cada linha da marts.fato_gastos representa um registro de gastos e expectativa de vida de um país em determinado ano.
A chave lógica da tabela fato é composta por:
 (id_calendario, id_pais)
Não pode existir mais de um registro para a mesma combinação de país e ano.
Motivo: A granularidade explícita impede duplicações acidentais nas agregações e garante consistência nas consultas analíticas.
2. NOMES
Todas as colunas devem utilizar português, snake_case.
Nenhuma coluna fora do mapa definido pode ser criada, exceto as chaves substitutas e os atributos derivados explicitamente especificados.
Origem (Refined)
refined.tb_gastos: ano id_pais gasto_usd expectativa_de_vida
refined.tb_paises: id_pais pais
Tabelas finais (Marts — Star Schema)
marts.d_calendario:
 id_calendario (Gerado automaticamente)
 ano (Integer)
marts.d_pais:
 id_pais (Integer - PK)
 pais (Varchar)
marts.fato_gastos:
 id_calendario (Integer - FK)
 id_pais (Integer - FK)
 gasto_usd (Decimal)
 expectativa_de_vida (Decimal)
Regras de relacionamento
•	marts.fato_gastos.id_calendario referencia marts.d_calendario.id_calendario.
•	marts.fato_gastos.id_pais referencia marts.d_pais.id_pais.
•	marts.d_calendario.ano deve ser único.
•	marts.d_pais.id_pais deve ser único.
•	marts.fato_gastos deve respeitar a unicidade da combinação (id_calendario, id_pais).
Mapeamento de colunas
refined.tb_gastos.ano -> marts.d_calendario.ano
refined.tb_gastos.id_pais -> marts.d_pais.id_pais
refined.tb_gastos.gasto_usd -> marts.fato_gastos.gasto_usd
refined.tb_gastos.expectativa_de_vida -> marts.fato_gastos.expectativa_de_vida
refined.tb_paises.pais -> marts.d_pais.pais
Motivo: A camada Marts não deve alterar o significado das métricas nem perder a identificação dos países e períodos de referência.
3. TIPOS
marts.d_calendario
•	id_calendario: INTEGER
•	ano: INTEGER
marts.d_pais
•	id_pais: INTEGER
•	pais: VARCHAR
marts.fato_gastos
•	id_calendario: INTEGER
•	id_pais: INTEGER
•	gasto_usd: DECIMAL(10,2)
•	expectativa_de_vida: DECIMAL(3,1)
Regras de geração dos atributos temporais
A dimensão calendário deve ser construída a partir dos anos distintos existentes em refined.tb_gastos.
Para cada ano:
•	ano: recebe o ano original.

A chave id_calendario deve ser gerada automaticamente, de maneira sequencial e determinística, ordenada pelo campo ano em ordem crescente.
Motivo: A dimensão calendário permite análises temporais sem exigir cálculos repetitivos nas consultas.
Regra para id_pais
A dimensão país deve preservar o identificador já existente em refined.tb_paises.
Portanto:
 marts.d_pais.id_pais = refined.tb_paises.id_pais
Não gerar novos identificadores para os países.
Motivo: Preservar a chave existente evita a necessidade de reconstruir os relacionamentos entre países e registros da tabela fato.
Regra para as métricas
As métricas devem preservar exatamente os valores existentes em refined.tb_gastos.
Não realizar:
•	Conversão de moeda.
•	Arredondamentos adicionais.
•	Multiplicações ou divisões.
•	Agregações.
•	Substituição de valores nulos.
O campo gasto_usd continua representando valores em dólar americano (USD).
4. CONVERSÃO QUE FALHA
Para todas as conversões de tipos, utilizar CAST explícito.
Nunca utilizar TRY_CAST, errors="coerce" ou mecanismos que transformem falhas de conversão em NULL.
As tabelas de origem já devem estar tipadas corretamente na camada Refined.
Caso alguma conversão falhe:
•	Informar a tabela de origem.
•	Informar a coluna.
•	Apresentar um exemplo do valor que não converteu.
•	Encerrar a execução com sys.exit(1).
Motivo: Uma falha de conversão não pode ser mascarada como um valor nulo legítimo.
5. DUPLICATAS E INTEGRIDADE
marts.d_calendario
Chave primária: id_calendario
Chave de negócio: ano
Não pode existir mais de um registro para o mesmo ano.
marts.d_pais
Chave primária: id_pais
Chave de negócio: pais
Não pode existir mais de um registro para o mesmo país.
Preservar os identificadores provenientes de refined.tb_paises.
marts.fato_gastos
Chave lógica composta: (id_calendario, id_pais)
Não pode existir mais de um registro para a mesma combinação de país e ano.
Tratamento
Linha inteira repetida: Mantém uma ocorrência e contabiliza quantas foram removidas.
Chave repetida com conteúdo diferente: Interrompe a execução, apresenta a chave e as linhas conflitantes e encerra com sys.exit(1).
Não escolher registros automaticamente. Não utilizar DISTINCT para esconder conflitos de negócio.
Integridade referencial
Antes de materializar a tabela fato, verificar:
•	Todo id_pais presente em refined.tb_gastos existe em refined.tb_paises.
•	Todo id_calendario utilizado pela fato existe em marts.d_calendario.
•	Todo id_pais utilizado pela fato existe em marts.d_pais.
Caso exista uma referência inválida: Informar a tabela, a chave e o registro inconsistente. Encerrar com sys.exit(1).
Motivo: A tabela fato não pode conter registros sem correspondência nas dimensões.
6. NULOS
Nenhuma linha é apagada por possuir valores nulos.
Nenhum nulo é preenchido artificialmente.
Regras:
•	marts.d_calendario: os atributos derivados devem ser nulos somente se a origem permitir um ano nulo, caso em que a regra de construção da dimensão deve interromper a execução, pois não é possível derivar década e século.
•	marts.d_pais: preservar valores nulos de acordo com a origem, sem criar países fictícios.
•	marts.fato_gastos: preservar os nulos de gasto_usd e expectativa_de_vida.
As chaves utilizadas nos relacionamentos devem ser obrigatórias e não podem ser nulas.
Caso ano, id_pais ou as chaves necessárias para relacionamento estejam nulas: Informar a tabela, a coluna e a quantidade de registros afetados. Encerrar com sys.exit(1).
Motivo: Valores nulos nas métricas representam fatos da origem, enquanto valores nulos nas chaves comprometem a integridade do modelo dimensional.
7. SAÍDA NA TELA
Exibir uma linha por tabela materializada, no formato:
 marts.d_calendario       51 -> 51 linhas (0 duplicatas)
 marts.d_pais              6 -> 6 linhas (0 duplicatas)
 marts.fato_gastos        274 -> 274 linhas (0 duplicatas)
Abaixo de cada tabela, apresentar as colunas que possuem nulos e suas respectivas contagens:
   nulos mantidos: gasto_usd 0, expectativa_de_vida 2
Apresentar também:
•	Quantidade de anos distintos.
•	Quantidade de países distintos.
•	Quantidade de registros na tabela fato.
•	Quantidade de duplicatas removidas.
•	Quantidade de registros rejeitados por inconsistência (quando houver interrupção).
As contagens devem vir do banco de dados.
Utilizar separador de milhar com ponto.
stdout deve ser reconfigurado para UTF-8.
Última linha:
 TOTAL: X tabelas materializadas, Y registros.
8. REEXECUÇÃO
Utilizar CREATE OR REPLACE TABLE.
Nunca utilizar INSERT INTO para acrescentar registros de uma execução anterior.
Cada execução deve reconstruir integralmente as três tabelas Marts.
A execução deve ser determinística:
•	Os mesmos dados na Refined devem produzir os mesmos registros na Marts.
•	Os identificadores de calendário devem manter a mesma correspondência com seus respectivos anos.
•	Os identificadores de país devem preservar os valores da Refined.
Rodar dez vezes = rodar uma vez.
9. ERROS E PRÉ-REQUISITOS
Antes de iniciar a transformação, verificar a existência das tabelas:
 refined.tb_gastos
 refined.tb_paises
Se alguma tabela estiver ausente:
 Informar exatamente qual tabela não foi encontrada.
 Orientar a execução do comando:

   uv run python -m pipeline.transformacao

 Encerrar com sys.exit(1).
Antes de materializar a camada Marts, validar:
•	Existência das colunas obrigatórias.
•	Tipos físicos compatíveis.
•	Unicidade das chaves das dimensões.
•	Unicidade da chave lógica da tabela fato.
•	Integridade referencial.
•	Ausência de nulos nas chaves obrigatórias.
Caso qualquer validação falhe, informar o problema e encerrar com sys.exit(1).
10. RESULTADO ESPERADO
Ao final da execução, o schema marts deverá conter exatamente três tabelas:
 marts.d_calendario
 marts.d_pais
 marts.fato_gastos
O relacionamento deverá seguir o modelo estrela:
               marts.d_calendario
                     |
                     | id_calendario
                     |
marts.d_pais ---- marts.fato_gastos id_pais id_pais
A tabela fato deverá concentrar as métricas quantitativas, enquanto as dimensões deverão fornecer o contexto temporal e geográfico para as análises.
A camada Marts será utilizada para consultas analíticas, indicadores, agregações e construção de dashboards.
Não criar tabelas adicionais no schema marts.
