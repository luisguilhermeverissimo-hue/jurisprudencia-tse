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

Certificados: no Windows, a extensão leva a lista de certificados da Mozilla (cacert.pem, do
certifi), e o lançador junta a ela os certificados do Windows numa lista só, entregue ao uv por
SSL_CERT_FILE. Uma fonte cobre a falha da outra:
- o Windows só baixa uma raiz pública quando algum programa do sistema precisa dela, então pode
  faltar a raiz do GitHub (o Edge e o Chrome usam lista própria e abrem o site normalmente);
- em redes com inspeção HTTPS (antivírus, firewall), o certificado da inspeção só está no Windows.
Sem o cacert.pem ao lado (Claude Code, rodando este arquivo direto do GitHub), o lançador usa os
certificados do Windows se eles reconhecerem o GitHub, e a lista própria do uv se não.

Só usa a biblioteca padrão do Python e não escreve nada na saída padrão, que é do protocolo MCP.
"""

import os
import re
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPOSITORIO = "luisguilhermeverissimo-hue/jurisprudencia-tse"
# Trocada pela versão do pacote ao gerar a extensão; usada só se não houver internet nem versão
# anterior guardada.
VERSAO_EMBUTIDA = "v0.0.0"
# Lista de certificados da Mozilla, copiada do certifi para a extensão ao empacotar.
CERTIFICADOS_MOZILLA = Path(__file__).with_name("cacert.pem")
# Uso "autenticação de servidor" (TLS) dos certificados do Windows.
OID_AUTENTICACAO_SERVIDOR = "1.3.6.1.5.5.7.3.1"


def _avisar(mensagem: str) -> None:
    print(f"[jurisprudencia-tse] {mensagem}", file=sys.stderr, flush=True)


def _pasta_dados() -> Path:
    return Path(
        os.environ.get("TSE_PASTA_DADOS")
        or Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "jurisprudencia-tse"
    )


def _arquivo_versao() -> Path:
    return _pasta_dados() / "versao-em-uso.txt"


def certificados_windows() -> list[str]:
    """Certificados das listas de raízes e intermediários do Windows aceitos para TLS, em PEM."""
    if not hasattr(ssl, "enum_certificates"):  # só existe no Windows
        return []
    vistos: set[bytes] = set()
    pems: list[str] = []
    for loja in ("ROOT", "CA"):
        try:
            itens = ssl.enum_certificates(loja)
        except OSError:
            continue
        for der, codificacao, confianca in itens:
            if codificacao != "x509_asn" or der in vistos:
                continue
            if confianca is not True and OID_AUTENTICACAO_SERVIDOR not in confianca:
                continue
            vistos.add(der)
            pems.append(ssl.DER_cert_to_PEM_cert(der))
    return pems


def preparar_certificados() -> Path | None:
    """Grava a lista Mozilla + Windows na pasta de dados e devolve o caminho; None se não houver."""
    if sys.platform != "win32" or not CERTIFICADOS_MOZILLA.is_file():
        return None
    try:
        mozilla = CERTIFICADOS_MOZILLA.read_text(encoding="utf-8")
    except OSError:
        return None
    conteudo = mozilla.rstrip() + "\n\n# Certificados do Windows\n" + "".join(certificados_windows())
    destino = _pasta_dados() / "certificados.pem"
    try:
        if destino.is_file() and destino.read_text(encoding="utf-8") == conteudo:
            return destino
        destino.parent.mkdir(parents=True, exist_ok=True)
        # O Claude abre o MCP em mais de um processo ao mesmo tempo: grava num arquivo próprio e
        # troca de uma vez, para o uv nunca ler a lista pela metade.
        temporario = destino.with_name(f"certificados-{os.getpid()}.tmp")
        temporario.write_text(conteudo, encoding="utf-8")
        try:
            os.replace(temporario, destino)
        except OSError:
            temporario.unlink(missing_ok=True)
            # Outro processo está gravando a mesma lista ou a mantém aberta: serve a que existe.
            return destino if destino.is_file() else None
    except OSError as erro:
        _avisar(f"não foi possível gravar a lista de certificados ({erro}).")
        return None
    return destino


def _falha_de_certificado(erro: BaseException) -> bool:
    return isinstance(getattr(erro, "reason", erro), ssl.SSLCertVerificationError)


def ultima_release(contexto: ssl.SSLContext | None = None) -> tuple[str | None, bool]:
    """Tag da release mais recente (pelo redirecionamento de /releases/latest, sem a API do GitHub)
    e se a consulta falhou por certificado não reconhecido."""
    pedido = urllib.request.Request(
        f"https://github.com/{REPOSITORIO}/releases/latest",
        method="HEAD",
        headers={"User-Agent": "jurisprudencia-tse-lancador"},
    )
    try:
        with urllib.request.urlopen(pedido, timeout=8, context=contexto) as resposta:
            achado = re.search(r"/releases/tag/(v\d[\w.\-]*)$", resposta.geturl())
            return (achado.group(1) if achado else None), False
    except Exception as erro:  # noqa: BLE001 - sem rede, segue com a versão guardada
        _avisar(f"não foi possível consultar a versão mais recente ({erro}).")
        return None, _falha_de_certificado(erro)


def escolher_versao(mais_recente: str | None) -> tuple[str, bool]:
    """Versão a rodar e se ela é nova neste computador (primeira execução dessa versão)."""
    arquivo = _arquivo_versao()
    try:
        anterior = arquivo.read_text(encoding="utf-8").strip()
    except OSError:
        anterior = ""
    versao = os.environ.get("TSE_VERSAO", "").strip() or mais_recente or anterior or VERSAO_EMBUTIDA
    if versao != anterior:
        try:
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            arquivo.write_text(versao, encoding="utf-8")
        except OSError:
            pass
    return versao, versao != anterior


def configurar_tls(ambiente: dict[str, str], certificados: Path | None, falha_certificado: bool) -> None:
    """Escolhe os certificados que o uv vai usar para baixar o servidor e as dependências."""
    if ambiente.get("SSL_CERT_FILE"):
        return  # lista escolhida pelo usuário
    if certificados:
        ambiente["SSL_CERT_FILE"] = str(certificados)
        return
    if falha_certificado:
        # Os certificados do Windows não reconhecem o GitHub (falta a raiz no Windows): a lista
        # própria do uv resolve. Com UV_NATIVE_TLS o uv usaria só a do Windows e falharia também.
        ambiente.pop("UV_NATIVE_TLS", None)
        ambiente.pop("UV_SYSTEM_CERTS", None)
        _avisar("o Windows não reconheceu o certificado do GitHub; usando a lista de certificados do uv.")
        return
    # Redes com inspeção HTTPS (antivírus, firewall) usam um certificado instalado no Windows que a
    # lista própria do uv não conhece ("invalid peer certificate: UnknownIssuer"). Estas variáveis
    # fazem o uv usar os certificados do sistema: UV_NATIVE_TLS nas versões antigas (como a que vem
    # no Claude Desktop) e UV_SYSTEM_CERTS nas novas.
    ambiente.setdefault("UV_NATIVE_TLS", "true")
    ambiente.setdefault("UV_SYSTEM_CERTS", "true")


def main() -> int:
    # O log do Claude lê a saída de erro em UTF-8; no Windows o padrão é cp1252 ("n�o foi possível").
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    uv = os.environ.get("UV") or shutil.which("uv")
    if not uv:
        _avisar("o uv não foi encontrado. Instale-o: https://docs.astral.sh/uv/")
        return 1
    ambiente = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")}
    certificados = None if ambiente.get("SSL_CERT_FILE") else preparar_certificados()
    contexto = None
    if certificados:
        try:
            contexto = ssl.create_default_context(cafile=str(certificados))
        except (OSError, ssl.SSLError) as erro:
            _avisar(f"lista de certificados inválida ({erro}); usando a do sistema.")
            certificados = None
    mais_recente, falha_certificado = (None, False)
    if not os.environ.get("TSE_VERSAO", "").strip():
        mais_recente, falha_certificado = ultima_release(contexto)
    configurar_tls(ambiente, certificados, falha_certificado)

    versao, nova = escolher_versao(mais_recente)
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
    return subprocess.call(comando, env=ambiente)


if __name__ == "__main__":
    sys.exit(main())
