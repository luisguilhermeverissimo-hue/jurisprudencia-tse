"""Chamadas HTTP diretas que o portal faz sem captcha: inteiro teor e listas de valores."""

import asyncio
import re
import time
from pathlib import Path

import httpx
from pypdf import PdfReader

from .config import (
    ESPERA_APOS_LIMITE,
    INTERVALO_DOWNLOADS,
    PASTA_INTEIRO_TEOR,
    URL_API_PESQUISA,
    URL_SERVICOS,
    USER_AGENT,
)

LISTAS = {"classes": "/classes", "relatores": "/relatorias", "eleicoes": "/eleicoes", "normas": "/normas"}


class ErroServico(RuntimeError):
    pass


class LimiteRequisicoes(ErroServico):
    pass


def extrair_pdf(corpo: bytes) -> bytes:
    """O servidor devolve o PDF dentro de um envelope multipart/form-data, mesmo com Content-Type PDF.

    Quando há excesso de requisições, devolve HTTP 200 com uma mensagem de texto no lugar do arquivo.
    """
    inicio = corpo.find(b"%PDF")
    if inicio < 0:
        mensagem = corpo[:300].decode("utf-8", errors="replace").strip()
        if "Excesso de requisi" in mensagem:
            raise LimiteRequisicoes(mensagem)
        raise ErroServico(f"Resposta sem PDF: {mensagem[:200]}")
    fim = corpo.rfind(b"%%EOF")
    if fim < inicio:
        raise ErroServico("PDF incompleto na resposta.")
    return corpo[inicio : fim + len(b"%%EOF")]


def _nome_arquivo(resposta: httpx.Response, codigo: int) -> str:
    disposicao = resposta.headers.get("content-disposition", "")
    achado = re.search(r'filename="?([^";]+)"?', disposicao)
    original = achado.group(1) if achado else "inteiroTeor.pdf"
    original = re.sub(r"[^\w.\-]", "_", original)
    return f"{codigo}_{original}"


class ServicosTSE:
    def __init__(self, pasta_pdf: Path = PASTA_INTEIRO_TEOR):
        self.pasta_pdf = pasta_pdf
        self._cliente = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=15.0),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        self._listas: dict[str, list] = {}
        self._ultimo_download = 0.0
        self._trava_download = asyncio.Lock()

    async def fechar(self) -> None:
        await self._cliente.aclose()

    async def listar(self, tipo: str) -> list:
        if tipo not in LISTAS:
            raise ValueError(f"tipo deve ser um de {list(LISTAS)}")
        if tipo not in self._listas:
            corpo = ["TSE"] if tipo == "normas" else []
            resposta = await self._cliente.post(URL_API_PESQUISA + LISTAS[tipo], json=corpo)
            resposta.raise_for_status()
            self._listas[tipo] = resposta.json()
        return self._listas[tipo]

    def pdf_em_cache(self, codigo: int) -> Path | None:
        achados = sorted(self.pasta_pdf.glob(f"{int(codigo)}_*.pdf"))
        return achados[0] if achados else None

    async def baixar_inteiro_teor(self, codigo: int) -> Path:
        codigo = int(codigo)
        if arquivo := self.pdf_em_cache(codigo):
            return arquivo
        async with self._trava_download:
            for tentativa in range(2):
                espera = INTERVALO_DOWNLOADS - (time.monotonic() - self._ultimo_download)
                if espera > 0:
                    await asyncio.sleep(espera)
                resposta = await self._cliente.get(f"{URL_SERVICOS}download/pdf/{codigo}")
                self._ultimo_download = time.monotonic()
                resposta.raise_for_status()
                try:
                    pdf = extrair_pdf(resposta.content)
                except LimiteRequisicoes:
                    if tentativa == 0:
                        await asyncio.sleep(ESPERA_APOS_LIMITE)
                        continue
                    raise LimiteRequisicoes(
                        "O TSE recusou o download por excesso de requisições. Aguarde cerca de 1 minuto."
                    )
                self.pasta_pdf.mkdir(parents=True, exist_ok=True)
                arquivo = self.pasta_pdf / _nome_arquivo(resposta, codigo)
                arquivo.write_bytes(pdf)
                return arquivo
        raise ErroServico("Download não concluído.")


def texto_do_pdf(arquivo: Path) -> str:
    """Extrai o texto do PDF e guarda ao lado, para não reprocessar."""
    cache = arquivo.with_suffix(".txt")
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    leitor = PdfReader(str(arquivo))
    paginas = []
    for numero, pagina in enumerate(leitor.pages, start=1):
        conteudo = (pagina.extract_text() or "").strip()
        paginas.append(f"[Página {numero}]\n{conteudo}")
    texto = "\n\n".join(paginas)
    cache.write_text(texto, encoding="utf-8")
    return texto
