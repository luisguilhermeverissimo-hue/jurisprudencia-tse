"""Citação ABNT e textos de referência, reproduzindo as regras do portal (copiarCitacaoABNT, gerarTextoCabecalho)."""

import re

from .config import URL_PORTAL, ROTA_PESQUISA

NOMES_TRIBUNAIS = {
    "TSE": "Tribunal Superior Eleitoral",
    "TRE-AC": "Tribunal Regional Eleitoral do Acre",
    "TRE-AL": "Tribunal Regional Eleitoral de Alagoas",
    "TRE-AP": "Tribunal Regional Eleitoral do Amapá",
    "TRE-AM": "Tribunal Regional Eleitoral do Amazonas",
    "TRE-BA": "Tribunal Regional Eleitoral da Bahia",
    "TRE-CE": "Tribunal Regional Eleitoral do Ceará",
    "TRE-DF": "Tribunal Regional Eleitoral do Distrito Federal",
    "TRE-ES": "Tribunal Regional Eleitoral do Espírito Santo",
    "TRE-GO": "Tribunal Regional Eleitoral de Goiás",
    "TRE-MA": "Tribunal Regional Eleitoral do Maranhão",
    "TRE-MT": "Tribunal Regional Eleitoral do Mato Grosso",
    "TRE-MS": "Tribunal Regional Eleitoral do Mato Grosso do Sul",
    "TRE-MG": "Tribunal Regional Eleitoral de Minas Gerais",
    "TRE-PA": "Tribunal Regional Eleitoral do Pará",
    "TRE-PB": "Tribunal Regional Eleitoral da Paraíba",
    "TRE-PR": "Tribunal Regional Eleitoral do Paraná",
    "TRE-PE": "Tribunal Regional Eleitoral de Pernambuco",
    "TRE-PI": "Tribunal Regional Eleitoral do Piauí",
    "TRE-RJ": "Tribunal Regional Eleitoral do Rio de Janeiro",
    "TRE-RN": "Tribunal Regional Eleitoral do Rio Grande do Norte",
    "TRE-RS": "Tribunal Regional Eleitoral do Rio Grande do Sul",
    "TRE-RO": "Tribunal Regional Eleitoral de Rondônia",
    "TRE-RR": "Tribunal Regional Eleitoral de Roraima",
    "TRE-SC": "Tribunal Regional Eleitoral de Santa Catarina",
    "TRE-SP": "Tribunal Regional Eleitoral de São Paulo",
    "TRE-SE": "Tribunal Regional Eleitoral de Sergipe",
    "TRE-TO": "Tribunal Regional Eleitoral de Tocantins",
}

_SO_PONTUACAO = re.compile(r"^[^a-zA-Z0-9]+$")


def _preenchido(valor: str | None) -> bool:
    return bool(valor) and not _SO_PONTUACAO.match(valor)


def formatar_case(texto: str) -> str:
    if "não especificad" in texto.lower():
        return texto
    return " ".join(palavra[:1].upper() + palavra[1:] for palavra in texto.lower().split(" "))


def _relatoria(decisao: dict, separador: str) -> str:
    relatores = decisao.get("relatores") or []
    if len(relatores) == 1:
        r = relatores[0]
        return f"{separador}Relator(a) {r.get('autoridade') or ''} {r.get('nome') or ''}".rstrip()
    partes = []
    for r in relatores[:2]:
        descricao = r.get("descricaoCompleta") or ""
        if "Designado" in descricao:
            descricao = descricao.replace("Relator Designado(a)", "Relator designado(a)")
        else:
            descricao = descricao.replace("relator", "Relator(a)")
        partes.append(f"{separador}{descricao}")
    return "".join(partes)


def _publicacao_abnt(publicacao: dict) -> str:
    texto = ""
    volume, numero = publicacao.get("numeroVolume"), publicacao.get("numeroPublicacao")
    if _preenchido(volume) and _preenchido(numero):
        texto += f" {volume.strip()}.{numero.strip()}"
    elif _preenchido(numero):
        texto += f" {numero.strip()}"
    if _preenchido(publicacao.get("dataPublicacao")):
        texto += f", data {publicacao['dataPublicacao']}"
    if _preenchido(publicacao.get("numeroPagina")):
        texto += f", pag. {publicacao['numeroPagina']}"
    return texto


def citacao_abnt(decisao: dict) -> str:
    """Mesma citação do botão "Copiar citação" do portal, sem a marcação HTML de destaque."""
    sigla = decisao.get("siglaTribunalJE") or "TSE"
    tribunal = NOMES_TRIBUNAIS.get(sigla, sigla)
    classe = decisao.get("nomeTipoProcesso") or decisao.get("descricaoClasse") or ""
    texto = f"BRASIL. {tribunal}. {formatar_case(classe)}"
    if decisao.get("numeroProcesso"):
        texto += f" {decisao['numeroProcesso']}/{decisao.get('siglaUF') or ''}"
    texto += _relatoria(decisao, ", ")
    texto += f", {decisao.get('descricaoTipoDecisao') or ''} de {decisao.get('dataDecisao') or ''}"
    publicacoes = decisao.get("publicacoes") or []
    if publicacoes:
        primeira = publicacoes[0]
        texto += f", Publicado no(a) {primeira.get('nomeFontePublicacao') or ''}{_publicacao_abnt(primeira)}"
    return texto


def cabecalho(decisao: dict) -> str:
    """Linha de referência que o portal acrescenta às cópias de ementa e decisão."""
    classe = decisao.get("nomeTipoProcesso") or decisao.get("descricaoClasse") or ""
    texto = f"{classe} nº{decisao.get('numeroProcesso') or ''}, {decisao.get('descricaoTipoDecisao') or ''}"
    texto += _relatoria(decisao, ", ")
    for p in decisao.get("publicacoes") or []:
        texto += f", Publicação: {p.get('siglaFontePublicacao') or ''} - {p.get('nomeFontePublicacao') or ''}"
        if p.get("numeroVolume"):
            texto += f", Tomo {p['numeroVolume']}"
        if p.get("dataPublicacao"):
            texto += f", {p['dataPublicacao']}"
    return texto + "."


def link_decisao(codigo: int | str) -> str:
    return f"{URL_PORTAL}{ROTA_PESQUISA}?codigoDecisao={codigo}&params=s"


def formatar_numero_unico(numero: str | None) -> str | None:
    if not numero:
        return None
    if len(numero) == 19:
        numero = "0" + numero
    if len(numero) == 20:
        return f"{numero[:7]}-{numero[7:9]}.{numero[9:13]}.{numero[13]}.{numero[14:16]}.{numero[16:20]}"
    return numero


def link_andamento(decisao: dict) -> str | None:
    """Mesmo destino do botão "Andamento Processual" do portal (consultaProcessual)."""
    origem = decisao.get("origemDecisao")
    if origem == "PJE" and decisao.get("numeroUnico"):
        return f"https://consultaunificadapje.tse.jus.br/#/public/resultado/{formatar_numero_unico(decisao['numeroUnico'])}"
    if origem == "SADP":
        uf = (decisao.get("siglaTribunalJE") or "TSE").replace("TRE-", "")
        protocolo = decisao.get("numeroProtocolo")
        if protocolo and protocolo != "0":
            return (
                "https://sadppush.tse.jus.br/sadpPush/ExibirDadosProcessoJurisprudencia.do"
                f"?nprot={protocolo}&comboTribunal={uf.lower()}"
            )
        return (
            f"https://sadppush.tse.jus.br/sadpPush/Pesquisa.do?comboTribunal={uf.lower()}"
            f"&acao=pesquisarNumProcesso&siglaTribunal={uf.lower()}&nomeTribunal={uf}"
            f"&tipoPesquisa=divProcesso&numProcesso={decisao.get('numeroProcesso') or ''}"
        )
    return None
