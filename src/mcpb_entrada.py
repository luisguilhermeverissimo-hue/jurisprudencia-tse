"""Ponto de entrada da extensão do Claude Desktop (.mcpb, tipo "uv").

O Claude Desktop roda este arquivo com o Python e as dependências que ele mesmo instala pelo uv.
Como o arquivo fica em src/, a pasta src já está no caminho de importação.
"""

from jurisprudencia_tse.servidor import main

if __name__ == "__main__":
    main()
