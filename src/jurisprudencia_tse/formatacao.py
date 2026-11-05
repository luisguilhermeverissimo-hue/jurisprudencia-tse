"""Texto devolvido ao Claude: enxuto na lista, completo quando se pede uma decisão."""

from .citacao import citacao_abnt, link_andamento, link_decisao
from .consulta import Filtros, normalizar_artigo, normalizar_inciso, normalizar_tribunais
import re

from .texto import ementa_sem_cabecalho, resumir

FACETAS = {
    "siglaTribunalJE.keyword": "Tribunais",
    "siglaClasse.keyword": "Classes",
    "relatores.nome.keyword": "Relatores",
    "anoEleicao": "Eleições",
    "assuntos.nomeAssunto.keyword": "Assuntos",
    "siglaUF.keyword": "UF",
    "tipoDecisaoColegiado.keyword": "Resultado da votação",
    "descricaoTipoDecisao.keyword": "Tipo de decisão",
    "selecionada.keyword": "Decisão em destaque (S/N)",
}


def identificacao(d: dict) -> str:
    sigla = d.get("siglaTipoProcesso") or d.get("siglaClasse") or ""
    texto = f"{sigla} nº {d.get('numeroProcesso') or '?'}"
    tribunal = d.get("siglaTribunalJE")
    if tribunal and tribunal != "TSE":
        texto = f"{tribunal} · {texto}"
    if d.get("siglaUF"):
        texto += f"/{d['siglaUF']}"
    return f"{texto} — {d.get('descricaoTipoDecisao') or ''}".strip()


def _relatores(d: dict) -> str:
    return "; ".join(r.get("descricaoCompleta") or r.get("nome") or "" for r in d.get("relatores") or [])


def _publicacao(d: dict) -> str:
    pubs = d.get("publicacoes") or []
    if not pubs:
        return "não informada"
    p = pubs[0]
    return f"{p.get('siglaFontePublicacao') or ''} {p.get('dataPublicacao') or ''}".strip()


_PREPOSICOES = {"de", "da", "do", "das", "dos", "e"}


def nome_municipio(nome: str) -> str:
    """'SÃO BENTO DO UNA' → 'São Bento do Una' (o .title() deixava 'Do' e 'De')."""
    palavras = nome.strip().lower().split()
    return " ".join(p if i and p in _PREPOSICOES else p[:1].upper() + p[1:] for i, p in enumerate(palavras))


def linha_metadados(d: dict) -> str:
    partes = []
    if d.get("nomeMunicipio"):
        partes.append(f"{nome_municipio(d['nomeMunicipio'])}/{d.get('siglaUF') or ''}")
    if rel := _relatores(d):
        partes.append(rel)
    partes.append(f"Julgamento: {d.get('dataDecisao') or '?'}")
    partes.append(f"Publicação: {_publicacao(d)}")
    if d.get("temInteiroTeorPDF"):
        paginas = d.get("quantidadePaginasPDF")
        partes.append(f"Inteiro teor: PDF{f' ({paginas} fls.)' if paginas and paginas != '0' else ''}")
    else:
        partes.append("Inteiro teor: indisponível")
    return " · ".join(partes)


def _dicas_sem_resultado(filtros: Filtros) -> list[str]:
    """Filtros que costumam zerar a pesquisa, com o próximo passo de cada um."""
    portal_, siglas = normalizar_tribunais(filtros.tribunais)
    tribunal = f", tribunal='{siglas[0] if siglas else ('TREs' if portal_ == 'tres' else 'TSE')}'"
    dicas = []
    if filtros.numero_processo:
        outro = "tribunais=['TREs']" if portal_ == "tse" else "o TSE (sem tribunais)"
        dicas.append(f"numero_processo: confira o número; se o processo for de outro portal, pesquise em {outro}.")
    if filtros.classes:
        dicas.append(f"classes {filtros.classes}: confira as siglas em tse_listar_valores('classes'{tribunal}); "
                     "cada tribunal tem as suas.")
    if filtros.relatores:
        dicas.append(f"relatores {filtros.relatores}: use o nome como em tse_listar_valores('relatores'{tribunal}).")
    if filtros.lei_numero or filtros.lei_ano or filtros.artigo or filtros.paragrafo or filtros.inciso or filtros.alinea:
        partes = [f"lei {filtros.lei_numero or '?'}" + (f"/{filtros.lei_ano}" if filtros.lei_ano else "")]
        if filtros.artigo:
            partes.append(f"art. {normalizar_artigo(filtros.artigo)}")
        if filtros.paragrafo:
            partes.append(f"§ {filtros.paragrafo}")
        if filtros.inciso:
            partes.append(f"inc. {normalizar_inciso(filtros.inciso, portal_)}")
        if filtros.alinea:
            partes.append(f"al. {filtros.alinea}")
        dicas.append(f"dispositivo ({', '.join(partes)}): o índice só traz o que a decisão citou expressamente; "
                     "tente só lei e artigo, ou passe o dispositivo para o texto.")
    if filtros.municipio:
        dicas.append(f"municipio '{filtros.municipio}': a comparação é exata com o nome no índice; confira a grafia.")
    if filtros.partes:
        dicas.append(f"partes '{filtros.partes}': nome com várias palavras é buscado como frase exata; "
                     "tente parte do nome ou a sigla.")
    if filtros.anos_eleicao or filtros.data_inicio or filtros.data_fim:
        dicas.append("período (anos_eleicao, datas): amplie o intervalo ou retire o filtro.")
    if filtros.texto or filtros.ementa_decisao:
        dicas.append("termos: use menos termos ligados por E, alternativas com OU ou sinonimos=True.")
    return dicas


def lista_resultados(resposta: dict, decisoes: list[dict], pagina: int, por_pagina: int,
                     ementa_completa: bool, incluir_facetas: bool, filtros: Filtros | None = None,
                     aviso: str | None = None) -> str:
    total = resposta.get("totalRegistros") or 0
    if total == 0:
        linhas = ["Nenhuma decisão encontrada."]
        dicas = _dicas_sem_resultado(filtros) if filtros else []
        if dicas:
            linhas.append("Filtros que podem ter restringido demais:")
            linhas += [f"- {dica}" for dica in dicas]
        else:
            linhas.append("Tente termos mais amplos, sinônimos ou menos filtros.")
        if aviso:
            linhas.append(aviso)
        return "\n".join(linhas)
    paginas = -(-min(total, 10_000) // por_pagina)
    linhas = [f"{total} decisões encontradas. Página {pagina} de {paginas} ({len(decisoes)} nesta página).", ""]
    for i, d in enumerate(decisoes, start=(pagina - 1) * por_pagina + 1):
        destaque = " ★ em destaque" if d.get("selecionada") == "S" else ""
        linhas.append(f"### {i}. {identificacao(d)} [codigoDecisao {d['codigoDecisao']}]{destaque}")
        linhas.append(linha_metadados(d))
        ementa = ementa_sem_cabecalho(d.get("textoEmenta"))
        if not ementa:
            ementa = "(sem ementa no portal; veja a decisão com tse_obter_decisao)"
        linhas.append("Ementa: " + (ementa if ementa_completa else resumir(ementa, 450)))
        linhas.append("")
    if resposta.get("mensagem"):
        linhas.append(f"Aviso do portal: {resposta['mensagem']}")
    if aviso:
        linhas.append(f"Aviso: {aviso}")
    if incluir_facetas:
        linhas.append(facetas(resposta))
    return "\n".join(linhas).strip()


# Sufixo de desambiguação do índice nos nomes de relator ("THURY_2", "Oliveira-_1").
_SUFIXO_INDICE = re.compile(r"[\s-]*_\d+$")
LIMITES_FACETAS = {"Tribunais": 27}


def _rotulo_faceta(rotulo: str, chave) -> str:
    chave = re.sub(r"\s+", " ", str(chave)).strip()
    return _SUFIXO_INDICE.sub("", chave) if rotulo == "Relatores" else chave


def facetas(resposta: dict, limite: int = 10) -> str:
    linhas = ["## Distribuição dos resultados"]
    for agregacao in resposta.get("aggs") or []:
        rotulo = FACETAS.get(agregacao.get("nome"))
        if not rotulo:
            continue
        # Junta valores que o índice separa só por espaço ou sufixo ("Abuso de poder " e "Abuso de poder").
        contagem: dict[str, int] = {}
        for bucket in agregacao.get("buckets") or []:
            chave = _rotulo_faceta(rotulo, bucket.get("key"))
            contagem[chave] = contagem.get(chave, 0) + int(bucket.get("docCount") or 0)
        ordenados = sorted(contagem.items(), key=lambda item: -item[1])
        maximo = LIMITES_FACETAS.get(rotulo, limite)
        itens = [f"{chave} ({quantidade})" for chave, quantidade in ordenados[:maximo]]
        if len(ordenados) > maximo:
            resto = sum(quantidade for _, quantidade in ordenados[maximo:])
            itens.append(f"mais {len(ordenados) - maximo} valores ({resto})")
        if itens:
            linhas.append(f"- {rotulo}: " + ", ".join(itens))
    linhas.append("(Valores mais frequentes devolvidos pelo portal; as contagens podem não somar o total.)")
    return "\n".join(linhas)


def decisao_completa(d: dict) -> str:
    linhas = [f"# {identificacao(d)}", f"codigoDecisao: {d['codigoDecisao']}"]
    if d.get("numeroUnicoFormatado"):
        linhas.append(f"Número único: {d['numeroUnicoFormatado']}")
    classe = d.get("nomeTipoProcesso") or d.get("descricaoClasse")
    if classe:
        linhas.append(f"Classe: {classe}")
    linhas.append(linha_metadados(d))
    if d.get("anoEleicao"):
        linhas.append(f"Eleição: {d['anoEleicao']}")
    if d.get("tipoDecisaoColegiado") and d["tipoDecisaoColegiado"] != "Sem anotação":
        linhas.append(f"Votação: {d['tipoDecisaoColegiado']}")
    linhas += ["", "## Ementa", d.get("textoEmenta") or "(sem ementa)", "", "## Decisão", d.get("textoDecisao") or "(sem texto)"]

    if d.get("textoObservacaoGeral"):
        linhas += ["", "## Observações", d["textoObservacaoGeral"]]
    if d.get("partes"):
        linhas += ["", "## Partes"]
        for p in d["partes"]:
            advogados = ", ".join(a.get("nomeAdvogado") or "" for a in p.get("advogados") or [])
            linhas.append(f"- {p.get('nomeParte')}" + (f" (adv.: {advogados})" if advogados else ""))
    if d.get("referenciasLegislativas"):
        linhas += ["", "## Referências legislativas"]
        for r in d["referenciasLegislativas"]:
            dispositivos = "; ".join(x.get("dispositivo") or "" for x in r.get("dispositivos") or [])
            linhas.append(f"- {r.get('legislacao')}" + (f" — {dispositivos}" if dispositivos else ""))
    if d.get("sumulas"):
        linhas += ["", "## Súmulas citadas"]
        for s in d["sumulas"]:
            enunciado = f": {s['descricaoEnunciado']}" if s.get("descricaoEnunciado") else ""
            linhas.append(f"- Súmula {s.get('numeroSumula')} do {s.get('siglaOrgaoProlator')}{enunciado}")
    if d.get("precedentes"):
        linhas += ["", "## Precedentes citados"]
        for p in d["precedentes"]:
            linhas.append(
                f"- {p.get('siglaTipoProcesso') or p.get('siglaClasse')} nº {p.get('numeroProcesso')}/{p.get('siglaUF')}, "
                f"{p.get('dataDecisao')}, {(p.get('nomeMinistroRelator') or '').strip()} "
                f"[codigoDecisao {p.get('codigoDecisaoPrecedente')}]"
            )
    if d.get("vides"):
        linhas += ["", "## Decisões relacionadas (vide)"]
        for v in d["vides"]:
            nota = f" — {v['textoNotaVide']}" if v.get("textoNotaVide") else ""
            linhas.append(
                f"- {v.get('siglaTipoProcesso')} nº {v.get('numeroProcesso')}/{v.get('siglaUF')}, "
                f"{v.get('dataDecisao')}{nota} [codigoDecisao {v.get('codigoDecisaoVide')}]"
            )
    if d.get("assuntos"):
        linhas += ["", "Assuntos: " + ", ".join(a.get("nomeAssunto") or "" for a in d["assuntos"])]

    linhas += ["", "## Citação (ABNT, formato do portal)", citacao_abnt(d), "", f"Link: {link_decisao(d['codigoDecisao'], d.get('siglaTribunalJE'))}"]
    if andamento := link_andamento(d):
        linhas.append(f"Andamento processual: {andamento}")
    return "\n".join(linhas)
