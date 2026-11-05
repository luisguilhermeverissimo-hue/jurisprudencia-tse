"""Limpeza dos textos devolvidos pela API (HTML e marcação de destaque dos termos pesquisados)."""

import html
import re

_DESTAQUE = re.compile(r"<span class=['\"]highlighted['\"]>(.*?)</span>", re.IGNORECASE | re.DOTALL)
_QUEBRA = re.compile(r"<\s*(br|/p|/div|/li|/h\d)\s*/?\s*>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_ESPACOS = re.compile(r"[ \t ]+")
_LINHAS_VAZIAS = re.compile(r"\n\s*\n\s*\n+")


def sem_destaque(valor: str | None) -> str | None:
    """Remove o <span class='highlighted'> que a API põe em volta dos termos pesquisados."""
    if valor is None:
        return None
    return _DESTAQUE.sub(r"\1", valor)


def html_para_texto(valor: str | None) -> str | None:
    """Converte ementa e decisão (HTML) em texto corrido, preservando os parágrafos."""
    if not valor:
        return valor
    texto = sem_destaque(valor)
    texto = texto.replace("\r", "")
    texto = _QUEBRA.sub("\n", texto)
    texto = _TAG.sub("", texto)
    texto = html.unescape(texto)
    # O TSE grava o hífen como travessão-ene ("vice–prefeito", "0600814–85"); o portal faz a mesma troca.
    texto = texto.replace("–", "-")
    linhas = [_ESPACOS.sub(" ", linha).strip() for linha in texto.split("\n")]
    texto = "\n".join(linhas)
    texto = _LINHAS_VAZIAS.sub("\n\n", texto)
    return texto.strip()


def limpar_valores(dado):
    """Aplica sem_destaque em todas as strings de uma estrutura JSON."""
    if isinstance(dado, str):
        return html.unescape(sem_destaque(dado))
    if isinstance(dado, list):
        return [limpar_valores(item) for item in dado]
    if isinstance(dado, dict):
        return {chave: limpar_valores(valor) for chave, valor in dado.items()}
    return dado


def resumir(texto: str | None, limite: int) -> str:
    if not texto:
        return ""
    texto = " ".join(texto.split())
    if len(texto) <= limite:
        return texto
    corte = texto.rfind(" ", 0, limite)
    return texto[: corte if corte > 0 else limite] + " […]"
