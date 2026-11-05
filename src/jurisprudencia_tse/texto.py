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
    texto = trocar_aspas_corrompidas(texto)
    linhas = [_ESPACOS.sub(" ", linha).strip() for linha in texto.split("\n")]
    texto = "\n".join(linhas)
    # Decisões antigas trazem quebras de linha no meio da frase ("configuração,\nhaja\nvista").
    texto = _QUEBRA_NO_MEIO.sub(" ", texto)
    texto = _LINHAS_VAZIAS.sub("\n\n", texto)
    return texto.strip()


# Quebra simples depois de algo que não fecha frase, seguida de minúscula que não abre item ("b)").
_QUEBRA_NO_MEIO = re.compile(r"(?<=[^\s.:;!?])\n(?=[a-zà-ü](?![a-z]?\)))")
_ASPAS_CORROMPIDAS = re.compile(r"¿([^¿\n]{1,300})¿")


def trocar_aspas_corrompidas(texto: str) -> str:
    """O portal entrega aspas curvas e travessões como "¿" ("¿conjunto da obra¿")."""
    if "¿" not in texto:
        return texto
    texto = _ASPAS_CORROMPIDAS.sub(r"“\1”", texto)
    return texto.replace(" ¿ ", " - ").replace("¿", '"')


_CABECALHO = re.compile(
    r"^(AC[ÓO]RD[ÃA]O|TRIBUNAL (SUPERIOR|REGIONAL) ELEITORAL.*|[A-Z]{2,5} \d+/\d+|"
    r".*\(PJe\).*|.*\bN[º°o]\.? ?\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}.*|"
    r"(RELATORA?|RECORRENTES?|RECORRID[AO]S?|AGRAVANTES?|AGRAVAD[AO]S?|ADVOGAD[AO]S?|EMBARGANTES?|"
    r"EMBARGAD[AO]S?|INVESTIGANTES?|INVESTIGAD[AO]S?|REPRESENTANTES?|REPRESENTAD[AO]S?|"
    r"IMPETRANTES?|IMPETRAD[AO]S?|REQUERENTES?|REQUERID[AO]S?|INTERESSAD[AO]S?|RECLAMANTES?|"
    r"PROCURADORA?)\b[^:]{0,40}:.*)$",
    re.IGNORECASE | re.DOTALL,
)
_ROTULO_EMENTA = re.compile(r"^\s*EMENTA\s*[:.\-]?\s*", re.IGNORECASE)


def ementa_sem_cabecalho(texto: str | None) -> str:
    """Tira da ementa o cabeçalho do PJe (acórdão, classe, relator, partes, advogados) e o rótulo "Ementa"."""
    if not texto:
        return ""
    paragrafos = texto.split("\n\n")
    while len(paragrafos) > 1 and _CABECALHO.match(paragrafos[0].strip()):
        paragrafos.pop(0)
    return _ROTULO_EMENTA.sub("", "\n\n".join(paragrafos), count=1).strip()


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
