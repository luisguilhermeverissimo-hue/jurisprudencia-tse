from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from jurisprudencia_tse.citacao import cabecalho, citacao_abnt, formatar_numero_unico, link_andamento
from jurisprudencia_tse.consulta import Filtros, FiltroInvalido, parametros, rota
from jurisprudencia_tse.decisoes import normalizar
from jurisprudencia_tse.servicos import ErroServico, LimiteRequisicoes, extrair_pdf
from jurisprudencia_tse.texto import html_para_texto, sem_destaque

# Metadados públicos do REspEl 060036447/RN, como devolvidos pela API em 26/10/2026 (resumidos).
DECISAO = {
    "siglaTribunalJE": "TSE",
    "codigoDecisao": 3580563,
    "numeroProcesso": "060036447",
    "dataDecisao": "03/09/2026",
    "siglaClasse": "REspEl",
    "descricaoClasse": "RECURSO ESPECIAL ELEITORAL",
    "siglaUF": "RN",
    "siglaTipoProcesso": "REspEl",
    "nomeTipoProcesso": "Recurso Especial Eleitoral",
    "descricaoTipoDecisao": "Acórdão",
    "numeroUnico": "06003644720246200023",
    "numeroUnicoFormatado": "0600364-47.2024.6.20.0023",
    "numeroProtocolo": "0",
    "origemDecisao": "PJE",
    "temInteiroTeorPDF": "true",
    "temInteiroTeorAudio": None,
    "textoEmenta": "<div>ELEIÇÕES 2024. AÇÃO <span class='highlighted'>DE</span> INVESTIGAÇÃO. VICE&ndash;PREFEITO.</div>"
    "<div>  \r\n  <br>1. Primeiro item.</div>",
    "textoDecisao": "<p>O Tribunal, por unanimidade, negou provimento.</p>",
    "partes": [
        {"nomeParte": "PARTE A", "tipoParte": "PARTE", "advogados": []},
        {"nomeParte": "PARTE A", "tipoParte": "PARTE", "advogados": []},
    ],
    "publicacoes": [
        {
            "numeroPublicacao": "165",
            "nomeFontePublicacao": "Diário <span class='highlighted'>de</span> Justiça Eletrônico",
            "numeroPagina": None,
            "siglaFontePublicacao": "DJE",
            "dataPublicacao": "21/09/2026",
            "numeroVolume": None,
        }
    ],
    "relatores": [
        {
            "autoridade": "Min.",
            "nome": "Floriano <span class='highlighted'>De</span> Azevedo Marques",
            "competencia": "Relator(a)",
            "descricaoCompleta": "Relator(a) Min. Floriano <span class='highlighted'>De</span> Azevedo Marques",
        }
    ],
}


def test_sem_destaque():
    assert sem_destaque("Diário <span class='highlighted'>de</span> Justiça") == "Diário de Justiça"


def test_html_para_texto_preserva_paragrafos_e_troca_travessao():
    texto = html_para_texto(DECISAO["textoEmenta"])
    assert texto == "ELEIÇÕES 2024. AÇÃO DE INVESTIGAÇÃO. VICE-PREFEITO.\n\n1. Primeiro item."


def test_normalizar_limpa_e_deduplica():
    d = normalizar(DECISAO)
    assert d["relatores"][0]["nome"] == "Floriano De Azevedo Marques"
    assert len(d["partes"]) == 1
    assert d["temInteiroTeorPDF"] is True
    assert d["temInteiroTeorAudio"] is False
    assert "<" not in d["textoDecisao"]


def test_citacao_abnt_igual_ao_portal_sem_html():
    # Texto copiado do botão "Copiar citação" do portal, com o HTML de destaque removido.
    esperado = (
        "BRASIL. Tribunal Superior Eleitoral. Recurso Especial Eleitoral 060036447/RN, "
        "Relator(a) Min. Floriano De Azevedo Marques, Acórdão de 03/09/2026, "
        "Publicado no(a) Diário de Justiça Eletrônico 165, data 21/09/2026"
    )
    assert citacao_abnt(normalizar(DECISAO)) == esperado


def test_cabecalho():
    assert cabecalho(normalizar(DECISAO)) == (
        "Recurso Especial Eleitoral nº060036447, Acórdão, Relator(a) Min. Floriano De Azevedo Marques, "
        "Publicação: DJE - Diário de Justiça Eletrônico, 21/09/2026."
    )


def test_link_andamento_pje():
    assert formatar_numero_unico("06003644720246200023") == "0600364-47.2024.6.20.0023"
    assert link_andamento(DECISAO).endswith("/#/public/resultado/0600364-47.2024.6.20.0023")


def test_parametros_pesquisa_avancada():
    p = parametros(
        Filtros(
            texto="propaganda antecipada",
            classes=["REspEl", "AREspEl"],
            data_inicio="01/01/2024",
            data_fim="31/12/2025",
            lei_numero="9504",
            lei_ano="1997",
            artigo="36",
            tipos_decisao=["Acórdão"],
            pagina=2,
            por_pagina=10,
        )
    )
    # Formato confirmado no portal em 26/10/2026: 57 acórdãos com estes filtros.
    assert p["classes"] == "REspEl,AREspEl"
    assert p["datas"] == "Julgamento_2024-01-01_2025-12-31_"
    assert p["leis"] == "_9504_1997_Art._36_Par.__Inc.__Let.__"
    assert p["tipoDecisao"] == "Acórdão"
    assert (p["pag"], p["tamPag"], p["ordenacao"], p["params"]) == ("2", "10", "dj_desc", "s")


def test_rota_codifica_e_inclui_nonce():
    r = rota(Filtros(texto="abuso de poder", relatores=["Cármen Lúcia"]))
    assert r.startswith("#/jurisprudencia/pesquisa?")
    consulta = parse_qs(urlsplit(r.replace("#", "", 1)).query)
    assert consulta["expressaoLivre"] == ["abuso de poder"]
    assert consulta["relatores"] == ["Cármen Lúcia"]
    assert "_n" in consulta
    assert "+" not in r and " " not in unquote(r).split("?")[0]


@pytest.mark.parametrize(
    "filtros",
    [
        Filtros(),
        Filtros(texto="x", por_pagina=7),
        Filtros(texto="x", data_inicio="2024/13/40"),
        Filtros(texto="x", tipos_decisao=["Despacho"]),
        Filtros(texto="x", pagina=500, por_pagina=25),
        Filtros(texto="x", lei_numero="95_04"),
    ],
)
def test_filtros_invalidos(filtros):
    with pytest.raises(FiltroInvalido):
        parametros(filtros)


def test_extrair_pdf_do_envelope_multipart():
    pdf = b"%PDF-1.7\nconteudo\n%%EOF"
    corpo = (
        b"--fronteira\r\nContent-Disposition: form-data; name=\"file\"; filename=\"inteiroTeor.pdf\"\r\n"
        b"Content-Type: application/octet-stream\r\n\r\n" + pdf + b"\r\n--fronteira--\r\n"
    )
    assert extrair_pdf(corpo) == pdf


def test_extrair_pdf_limite_de_requisicoes():
    corpo = "Erro ao tentar recuperar PDF: Excesso de requisições! Favor aguardar alguns instantes.".encode()
    with pytest.raises(LimiteRequisicoes):
        extrair_pdf(corpo)
    with pytest.raises(ErroServico):
        extrair_pdf(b"<html>erro</html>")


# --- TREs (portal jurisprudencia-tres.tse.jus.br) ---

from jurisprudencia_tse.citacao import link_decisao  # noqa: E402
from jurisprudencia_tse.consulta import normalizar_tribunais, portal  # noqa: E402
from jurisprudencia_tse.formatacao import identificacao  # noqa: E402


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        (None, ("tse", [])),
        (["TSE"], ("tse", [])),
        (["tre-pe"], ("tres", ["TRE-PE"])),
        (["TRE PE", "TRE/PB", "TRE-PE"], ("tres", ["TRE-PE", "TRE-PB"])),
        (["TREs"], ("tres", [])),
        (["TRE-PE", "TREs"], ("tres", [])),
    ],
)
def test_normalizar_tribunais(entrada, esperado):
    assert normalizar_tribunais(entrada) == esperado


@pytest.mark.parametrize("entrada", [["TSE", "TRE-PE"], ["TRE-XX"], ["STF"]])
def test_normalizar_tribunais_invalidos(entrada):
    with pytest.raises(FiltroInvalido):
        normalizar_tribunais(entrada)


def test_parametros_tres_com_tribunal_e_municipio():
    filtros = Filtros(texto="abuso de poder", tribunais=["TRE-PE", "TRE-PB"], municipio="  são bento  do una ")
    p = parametros(filtros)
    assert portal(filtros) == "tres"
    assert p["tribunais"] == "TRE-PE,TRE-PB"
    assert p["municipio"] == "SÃO BENTO DO UNA"


def test_parametros_todos_os_tres_sem_filtro_de_tribunal():
    filtros = Filtros(texto="abuso", tribunais=["TREs"])
    assert portal(filtros) == "tres"
    assert "tribunais" not in parametros(filtros)


def test_tribunal_sozinho_nao_e_criterio():
    with pytest.raises(FiltroInvalido):
        parametros(Filtros(tribunais=["TRE-PE"]))


def test_link_e_identificacao_de_decisao_de_tre():
    assert link_decisao(3615272, "TRE-AP").startswith("https://jurisprudencia-tres.tse.jus.br/#/")
    assert link_decisao(3580563).startswith("https://jurisprudencia.tse.jus.br/#/")
    d = {"siglaTribunalJE": "TRE-PE", "siglaClasse": "REl", "numeroProcesso": "060044214",
         "siglaUF": "PE", "descricaoTipoDecisao": "Acórdão"}
    assert identificacao(d) == "TRE-PE · REl nº 060044214/PE — Acórdão"
    assert identificacao({**d, "siglaTribunalJE": "TSE"}).startswith("REl nº")
