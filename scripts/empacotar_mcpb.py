"""Gera a extensão do Claude Desktop: dist/jurisprudencia-tse.mcpb.

A extensão é só o lançador (mcpb/lancador.py): a cada início ele roda a release mais recente do
GitHub, então a extensão não precisa ser reinstalada a cada versão. Copia para build/mcpb só os
arquivos da lista abaixo e empacota com a ferramenta oficial @anthropic-ai/mcpb (precisa do Node.js).
Uso:
    .venv\\Scripts\\python scripts\\empacotar_mcpb.py
"""

import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_PACOTE = RAIZ / "build" / "mcpb"
SAIDA = RAIZ / "dist" / "jurisprudencia-tse.mcpb"
MCPB = "@anthropic-ai/mcpb@2.1.2"

# origem no repositório -> destino no pacote
ARQUIVOS = {
    "mcpb/manifest.json": "manifest.json",
    "mcpb/pyproject.toml": "pyproject.toml",
    "mcpb/lancador.py": "lancador.py",
    "README.md": "README.md",
    "LICENSE": "LICENSE",
}


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
    for origem, destino in ARQUIVOS.items():
        shutil.copy2(RAIZ / origem, PASTA_PACOTE / destino)

    # Versão usada pelo lançador só quando não houver internet nem versão anterior guardada.
    lancador = PASTA_PACOTE / "lancador.py"
    texto, trocas = re.subn(r'^VERSAO_EMBUTIDA = ".*"$', f'VERSAO_EMBUTIDA = "v{versao}"',
                            lancador.read_text(encoding="utf-8"), flags=re.M)
    if trocas != 1:
        sys.exit("VERSAO_EMBUTIDA não encontrada em mcpb/lancador.py.")
    lancador.write_text(texto, encoding="utf-8")
    pyproject = PASTA_PACOTE / "pyproject.toml"
    pyproject.write_text(pyproject.read_text(encoding="utf-8").replace('version = "0.0.0"', f'version = "{versao}"'),
                         encoding="utf-8")

    SAIDA.parent.mkdir(exist_ok=True)
    _npx("validate", str(PASTA_PACOTE / "manifest.json"))
    _npx("pack", str(PASTA_PACOTE), str(SAIDA))
    print(f"\nGerado: {SAIDA}")


if __name__ == "__main__":
    main()
