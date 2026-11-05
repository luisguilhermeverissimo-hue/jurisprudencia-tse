"""Gera a extensão do Claude Desktop: dist/jurisprudencia-tse.mcpb.

Copia para build/mcpb só os arquivos da lista abaixo (nada de .venv, cache, testes ou arquivos
soltos na pasta) e empacota com a ferramenta oficial @anthropic-ai/mcpb, que precisa do Node.js.
Uso:
    .venv\\Scripts\\python scripts\\empacotar_mcpb.py
"""

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_PACOTE = RAIZ / "build" / "mcpb"
SAIDA = RAIZ / "dist" / "jurisprudencia-tse.mcpb"
MCPB = "@anthropic-ai/mcpb@2.1.2"

ARQUIVOS = ["pyproject.toml", "uv.lock", "README.md", "LICENSE", "src/mcpb_entrada.py"]
PACOTE_PYTHON = "src/jurisprudencia_tse"


def _npx(*argumentos: str) -> None:
    npx = shutil.which("npx") or sys.exit("Node.js (npx) não encontrado. Instale o Node.js LTS.")
    subprocess.run([npx, "--yes", MCPB, *argumentos], check=True)


def main() -> None:
    versao = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    manifesto = json.loads((RAIZ / "mcpb" / "manifest.json").read_text(encoding="utf-8"))
    if manifesto["version"] != versao:
        sys.exit(f"Versões diferentes: pyproject {versao}, mcpb/manifest.json {manifesto['version']}.")

    shutil.rmtree(PASTA_PACOTE, ignore_errors=True)
    PASTA_PACOTE.mkdir(parents=True)
    shutil.copy2(RAIZ / "mcpb" / "manifest.json", PASTA_PACOTE / "manifest.json")
    for nome in ARQUIVOS:
        destino = PASTA_PACOTE / nome
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(RAIZ / nome, destino)
    shutil.copytree(
        RAIZ / PACOTE_PYTHON, PASTA_PACOTE / PACOTE_PYTHON, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )

    SAIDA.parent.mkdir(exist_ok=True)
    _npx("validate", str(PASTA_PACOTE / "manifest.json"))
    _npx("pack", str(PASTA_PACOTE), str(SAIDA))
    print(f"\nGerado: {SAIDA}")


if __name__ == "__main__":
    main()
