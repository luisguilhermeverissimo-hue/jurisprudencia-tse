"""Normalização das decisões devolvidas pela pesquisa e cache em disco.

A pesquisa já traz ementa e decisão completas (o "Mostrar mais" do portal só expande o texto),
então cada decisão vista numa pesquisa fica guardada e pode ser consultada depois sem nova busca.
"""

import json
from pathlib import Path

from .config import PASTA_DECISOES
from .texto import html_para_texto, limpar_valores

CAMPOS_HTML = (
    "textoEmenta",
    "textoDecisao",
    "textoObservacaoGeral",
    "textoIndexacaoLegado",
    "textoVotoVencidoLegado",
    "textoVotoVistaLegado",
    "textoDoutrinaLegado",
    "textoObservacaoLegado",
)


def normalizar(bruta: dict) -> dict:
    """Remove HTML e destaques, deduplica partes e converte flags de string para bool."""
    d = {chave: valor for chave, valor in bruta.items() if chave not in CAMPOS_HTML}
    d = limpar_valores(d)
    for campo in CAMPOS_HTML:
        d[campo] = html_para_texto(bruta.get(campo))

    if d.get("partes"):
        vistos, unicas = set(), []
        for parte in d["partes"]:
            chave = json.dumps(parte, sort_keys=True, ensure_ascii=False)
            if chave not in vistos:
                vistos.add(chave)
                unicas.append(parte)
        d["partes"] = unicas

    d["temInteiroTeorPDF"] = str(bruta.get("temInteiroTeorPDF")).lower() == "true"
    d["temInteiroTeorAudio"] = str(bruta.get("temInteiroTeorAudio")).lower() == "true"
    return d


class CacheDecisoes:
    def __init__(self, pasta: Path = PASTA_DECISOES):
        self.pasta = pasta
        self._memoria: dict[int, dict] = {}

    def _arquivo(self, codigo: int) -> Path:
        return self.pasta / f"{int(codigo)}.json"

    def guardar(self, decisao: dict) -> None:
        codigo = int(decisao["codigoDecisao"])
        self._memoria[codigo] = decisao
        self.pasta.mkdir(parents=True, exist_ok=True)
        self._arquivo(codigo).write_text(json.dumps(decisao, ensure_ascii=False), encoding="utf-8")

    def obter(self, codigo: int) -> dict | None:
        codigo = int(codigo)
        if codigo in self._memoria:
            return self._memoria[codigo]
        arquivo = self._arquivo(codigo)
        if arquivo.exists():
            decisao = json.loads(arquivo.read_text(encoding="utf-8"))
            self._memoria[codigo] = decisao
            return decisao
        return None
