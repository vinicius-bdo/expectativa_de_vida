"""Baixa quando necessário e ingere o CSV público, sem transformar os dados.

O arquivo healthexp.csv é lido de raw/ quando já existe, evitando tráfego
desnecessário e preservando a cópia local. Quando falta, é baixado da URL
oficial para um temporário dentro de raw/ e só passa a ser o arquivo de
entrada após o download terminar; assim uma falha não trunca nem substitui
um CSV utilizável. O temporário é removido ao final para não poluir a pasta.
A aquisição e a leitura terminam antes de abrir o DuckDB, para que uma falha
de rede ou de CSV não deixe uma ingestão parcial. O destino único é
raw.gastos, e a tabela é recriada a cada execução para tornar a repetição
segura.
O CSV é lido com UTF-8 e dtype=str, mantendo campos vazios como nulos e sem
descartar linhas ou alterar colunas e valores; conversões pertencem à etapa
refined. A saída usa contagem consultada no banco e stdout UTF-8 para
conferência no terminal do Windows.
"""

import shutil
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pandas as pd

from pipeline.db import PASTA_RAW, conectar, criar_schema, gravar

URL_CSV = "https://www.timestored.com/data/sample/healthexp.csv"


def _baixar_arquivo(arquivo: Path):
    temporario = None
    try:
        PASTA_RAW.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{arquivo.name}.",
            suffix=".tmp",
            dir=PASTA_RAW,
            delete=False,
        ) as destino:
            temporario = Path(destino.name)
            with urlopen(URL_CSV) as resposta:
                shutil.copyfileobj(resposta, destino)
            destino.flush()
        temporario.replace(arquivo)
    except (HTTPError, URLError, OSError) as erro:
        print(f"Falha ao baixar {URL_CSV}: {erro}")
        sys.exit(1)
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    arquivo = PASTA_RAW / "healthexp.csv"
    if not arquivo.is_file():
        _baixar_arquivo(arquivo)

    df = pd.read_csv(arquivo, encoding="utf-8", dtype=str)
    con = conectar()
    try:
        criar_schema(con, "raw")
        quantidade = gravar(con, df, "raw", "gastos")
    finally:
        con.close()

    print(f"raw.gastos: {quantidade:,} linhas".replace(",", "."))
    print(f"Total: {quantidade:,} linhas".replace(",", "."))


if __name__ == "__main__":
    main()
