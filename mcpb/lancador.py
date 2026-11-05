# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Lançador do MCP jurisprudencia-tse com atualização automática.

É o que a extensão do Claude Desktop (.mcpb) executa, e também pode ser usado no Claude Code.
A cada início, pergunta ao GitHub qual é a release mais recente do projeto e roda essa versão
pelo uv (`uv tool run --from <zip da release>`). Assim, publicar uma release nova no GitHub
atualiza todos os usuários na próxima vez que abrirem o Claude, sem baixar arquivo.

- O link do zip muda a cada versão; enquanto a versão é a mesma, o uv reaproveita o ambiente já
  montado e o início é rápido. Só a primeira abertura depois de uma versão nova demora mais.
- Sem internet, usa a última versão que já rodou neste computador.
- Para fixar uma versão (por exemplo, voltar atrás), defina TSE_VERSAO=v0.3.0.

Só usa a biblioteca padrão do Python e não escreve nada na saída padrão, que é do protocolo MCP.
"""

import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

REPOSITORIO = "luisguilhermeverissimo-hue/jurisprudencia-tse"
# Trocada pela versão do pacote ao gerar a extensão; usada só se não houver internet nem versão
# anterior guardada.
VERSAO_EMBUTIDA = "v0.0.0"


def _avisar(mensagem: str) -> None:
    print(f"[jurisprudencia-tse] {mensagem}", file=sys.stderr, flush=True)


def _arquivo_versao() -> Path:
    base = os.environ.get("TSE_PASTA_DADOS") or Path(
        os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share"
    ) / "jurisprudencia-tse"
    return Path(base) / "versao-em-uso.txt"


def ultima_release() -> str | None:
    """Tag da release mais recente, pelo redirecionamento de /releases/latest (sem a API do GitHub)."""
    pedido = urllib.request.Request(
        f"https://github.com/{REPOSITORIO}/releases/latest",
        method="HEAD",
        headers={"User-Agent": "jurisprudencia-tse-lancador"},
    )
    try:
        with urllib.request.urlopen(pedido, timeout=8) as resposta:
            achado = re.search(r"/releases/tag/(v\d[\w.\-]*)$", resposta.geturl())
            return achado.group(1) if achado else None
    except Exception as erro:  # noqa: BLE001 - sem rede, segue com a versão guardada
        _avisar(f"não foi possível consultar a versão mais recente ({erro}).")
        return None


def escolher_versao() -> tuple[str, bool]:
    """Versão a rodar e se ela é nova neste computador (primeira execução dessa versão)."""
    arquivo = _arquivo_versao()
    try:
        anterior = arquivo.read_text(encoding="utf-8").strip()
    except OSError:
        anterior = ""
    versao = os.environ.get("TSE_VERSAO", "").strip() or ultima_release() or anterior or VERSAO_EMBUTIDA
    if versao != anterior:
        try:
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            arquivo.write_text(versao, encoding="utf-8")
        except OSError:
            pass
    return versao, versao != anterior


def main() -> int:
    uv = os.environ.get("UV") or shutil.which("uv")
    if not uv:
        _avisar("o uv não foi encontrado. Instale-o: https://docs.astral.sh/uv/")
        return 1
    versao, nova = escolher_versao()
    origem = f"https://github.com/{REPOSITORIO}/archive/refs/tags/{versao}.zip"
    comando = [uv, "tool", "run", "--from", origem, "jurisprudencia-tse"]
    if nova:
        # O ambiente montado pelo uv fica numa pasta em que o Python não grava os .pyc; sem compilar
        # na instalação, cada início recompila tudo (vários segundos). Compilar em toda execução
        # também custa caro, então só na primeira execução de cada versão.
        comando[3:3] = ["--compile-bytecode"]
        _avisar(f"versão nova: {versao}. A primeira abertura prepara o ambiente e pode demorar.")
    else:
        _avisar(f"iniciando a versão {versao}.")
    ambiente = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")}
    # Redes com inspeção HTTPS (antivírus, firewall) usam um certificado instalado no Windows que a
    # lista própria do uv não conhece ("invalid peer certificate: UnknownIssuer"). Estas variáveis
    # fazem o uv usar os certificados do sistema: UV_NATIVE_TLS nas versões antigas (como a que vem
    # no Claude Desktop) e UV_SYSTEM_CERTS nas novas.
    ambiente.setdefault("UV_NATIVE_TLS", "true")
    ambiente.setdefault("UV_SYSTEM_CERTS", "true")
    return subprocess.call(comando, env=ambiente)


if __name__ == "__main__":
    sys.exit(main())
