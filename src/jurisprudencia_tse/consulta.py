"""Montagem do endereço de pesquisa do portal (link persistente).

O MCP não monta a query Elasticsearch: passa os filtros pela URL, como faz o próprio portal,
e deixa o front-end gerar a consulta e o token hCaptcha. Formato dos parâmetros em
util.criarFormLinkPersistente (docs/MAPEAMENTO_API_PORTAL_TSE.md).
"""

import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import quote, urlencode

from .config import ROTA_PESQUISA

TIPOS_DECISAO = ("Acórdão", "Decisão monocrática", "Sentença", "Resolução", "Decisão sem resolução")
TIPOS_DECISAO_PADRAO = ("Acórdão", "Resolução", "Decisão sem resolução")
TAMANHOS_PAGINA = (1, 10, 25, 50, 100, 250)
ORDENACOES = {
    "relevancia": "re",
    "julgamento_recentes": "dj_desc",
    "julgamento_antigas": "dj_asc",
    "publicacao_recentes": "dp_desc",
    "publicacao_antigas": "dp_asc",
}
# O portal não avança além da janela de 10.000 registros do Elasticsearch.
MAXIMO_REGISTROS = 10_000


class FiltroInvalido(ValueError):
    pass


@dataclass
class Filtros:
    texto: str | None = None
    incluir_inteiro_teor: bool = False
    sinonimos: bool = False
    codigo_decisao: int | None = None
    numero_processo: str | None = None
    relatores: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    anos_eleicao: list[str] = field(default_factory=list)
    ementa_decisao: str | None = None
    partes: str | None = None
    uf: str | None = None
    data_inicio: str | None = None
    data_fim: str | None = None
    tipo_data: str = "julgamento"
    lei_numero: str | None = None
    lei_ano: str | None = None
    artigo: str | None = None
    paragrafo: str | None = None
    inciso: str | None = None
    alinea: str | None = None
    tipos_decisao: list[str] = field(default_factory=lambda: list(TIPOS_DECISAO_PADRAO))
    ordenacao: str = "julgamento_recentes"
    pagina: int = 1
    por_pagina: int = 10


def _data_iso(valor: str, nome: str) -> str:
    valor = valor.strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(valor, formato).date().isoformat()
        except ValueError:
            continue
    raise FiltroInvalido(f"{nome} inválida: {valor!r}. Use dd/mm/aaaa.")


def _sem_separador(valor: str | None, nome: str) -> str:
    if valor is None:
        return ""
    valor = str(valor).strip()
    if "_" in valor:
        raise FiltroInvalido(f"{nome} não pode conter '_'.")
    return valor


def _lista(valores: list[str], nome: str) -> str:
    itens = [v.strip() for v in valores if v and v.strip()]
    if any("," in v for v in itens):
        raise FiltroInvalido(f"Os valores de {nome} não podem conter vírgula.")
    return ",".join(itens)


def parametros(filtros: Filtros) -> dict[str, str]:
    """Converte os filtros nos parâmetros de URL lidos pelo portal."""
    p: dict[str, str] = {}

    if filtros.codigo_decisao is not None:
        p["codigoDecisao"] = str(int(filtros.codigo_decisao))
    if filtros.texto and filtros.texto.strip():
        p["expressaoLivre"] = filtros.texto.strip()
    if filtros.incluir_inteiro_teor:
        p["inteiroTeor"] = "true"
    if filtros.sinonimos:
        p["sinonimos"] = "true"
    if filtros.numero_processo:
        p["numero"] = re.sub(r"\s+", "", filtros.numero_processo)
    if filtros.relatores:
        p["relatores"] = _lista(filtros.relatores, "relatores")
    if filtros.classes:
        p["classes"] = _lista(filtros.classes, "classes")
    if filtros.anos_eleicao:
        p["eleicoes"] = _lista([str(a) for a in filtros.anos_eleicao], "anos_eleicao")
    if filtros.ementa_decisao:
        p["ementaDec"] = filtros.ementa_decisao.strip()
    if filtros.partes:
        p["partes"] = filtros.partes.strip()
    if filtros.uf:
        p["uf"] = filtros.uf.strip().upper()

    if filtros.data_inicio or filtros.data_fim:
        if filtros.tipo_data not in ("julgamento", "publicacao"):
            raise FiltroInvalido("tipo_data deve ser 'julgamento' ou 'publicacao'.")
        tipo = "Julgamento" if filtros.tipo_data == "julgamento" else "Publicação"
        inicio = _data_iso(filtros.data_inicio, "data_inicio") if filtros.data_inicio else "null"
        fim = _data_iso(filtros.data_fim, "data_fim") if filtros.data_fim else "null"
        # O portal descarta o último segmento após o "_" final.
        p["datas"] = f"{tipo}_{inicio}_{fim}_"

    dispositivos = (filtros.artigo, filtros.paragrafo, filtros.inciso, filtros.alinea)
    if filtros.lei_numero or filtros.lei_ano or any(dispositivos):
        segmentos = [
            "",  # nome da norma: número e ano bastam e evitam erro de grafia
            _sem_separador(filtros.lei_numero, "lei_numero"),
            _sem_separador(filtros.lei_ano, "lei_ano"),
        ]
        for rotulo, valor in zip(("Art.", "Par.", "Inc.", "Let."), dispositivos):
            segmentos += [rotulo, _sem_separador(valor, rotulo)]
        p["leis"] = "_".join(segmentos) + "_"

    tipos = filtros.tipos_decisao or list(TIPOS_DECISAO_PADRAO)
    invalidos = [t for t in tipos if t not in TIPOS_DECISAO]
    if invalidos:
        raise FiltroInvalido(f"Tipos de decisão inválidos: {invalidos}. Válidos: {list(TIPOS_DECISAO)}")
    p["tipoDecisao"] = ",".join(tipos)

    criterios = set(p) - {"tipoDecisao"}
    if not criterios:
        raise FiltroInvalido("Informe ao menos um critério de pesquisa (texto, número, relator, classe, data etc.).")

    if filtros.ordenacao not in ORDENACOES:
        raise FiltroInvalido(f"ordenacao deve ser uma de {list(ORDENACOES)}.")
    if filtros.por_pagina not in TAMANHOS_PAGINA:
        raise FiltroInvalido(f"por_pagina deve ser um de {list(TAMANHOS_PAGINA)}.")
    if filtros.pagina < 1:
        raise FiltroInvalido("pagina começa em 1.")
    if filtros.pagina * filtros.por_pagina > MAXIMO_REGISTROS:
        raise FiltroInvalido("O portal não pagina além de 10.000 registros. Refine a pesquisa.")

    p["params"] = "s"
    p["ordenacao"] = ORDENACOES[filtros.ordenacao]
    p["pag"] = str(filtros.pagina)
    p["tamPag"] = str(filtros.por_pagina)
    return p


def rota(filtros: Filtros) -> str:
    """Fragmento de URL (#/...) que dispara a pesquisa no portal.

    O parâmetro "_n" é ignorado pelo portal; só garante que a mesma pesquisa repetida
    mude o endereço e volte a disparar.
    """
    p = parametros(filtros)
    p["_n"] = str(time.time_ns())
    return f"{ROTA_PESQUISA}?{urlencode(p, quote_via=quote, safe='')}"
