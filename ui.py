"""Abre a interface web da extensão ui do DuckDB para o banco do projeto.

O caminho é relativo a este arquivo para que o comando funcione a partir de
qualquer diretório. A conexão só é aberta se o banco já existir, pois criar
um banco vazio aparentaria uma ingestão mal sucedida.
A extensão é instalada/carregada na própria conexão e start_ui() inicia o
servidor local. O processo aguarda Ctrl+C porque a interface depende da
conexão viva; nesse encerramento, a conexão é fechada para liberar o lock do
arquivo antes de uma nova ingestão.
A espera usa pausas curtas em vez de uma espera de threading, pois a segunda
pode não responder a Ctrl+C no Python 3.12 para Windows.
O stdout é reconfigurado para UTF-8 para exibir corretamente as instruções
no Prompt de Comando do Windows.
"""

import sys
import time
from pathlib import Path

import duckdb


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    banco = Path(__file__).resolve().parent / "expectativa_de_vida.duckdb"
    if not banco.is_file():
        print(
            "Banco expectativa_de_vida.duckdb não encontrado. "
            "É preciso rodar a ingestão antes."
        )
        sys.exit(1)

    con = duckdb.connect(str(banco))
    try:
        con.execute("INSTALL ui")
        con.execute("LOAD ui")
        con.execute("CALL start_ui()")
        print("Interface disponível em http://localhost:4213")
        print("Ctrl+C para encerrar")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        con.close()


if __name__ == "__main__":
    main()
