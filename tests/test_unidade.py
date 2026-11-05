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


# --- 0.3.1: grafias que o índice do portal usa (bateria de 05/11/2026) -------------------------

from jurisprudencia_tse.consulta import (  # noqa: E402
    inciso_alternativo,
    normalizar_alinea,
    normalizar_artigo,
    normalizar_inciso,
    normalizar_numero_processo,
    normalizar_paragrafo,
    normalizar_partes,
    romano_para_arabico,
)
from jurisprudencia_tse.formatacao import lista_resultados  # noqa: E402


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [("41-A", "41A"), ("art. 36-a", "36A"), ("41 A", "41A"), ("1º", "1"), ("73", "73"), ("Art. 22", "22")],
)
def test_normalizar_artigo(entrada, esperado):
    assert normalizar_artigo(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [("§ 3º", "3"), ("10", "10"), ("parágrafo único", "único"), ("p.u.", "único"), ("Unico", "único")],
)
def test_normalizar_paragrafo(entrada, esperado):
    assert normalizar_paragrafo(entrada) == esperado


def test_romanos():
    assert [romano_para_arabico(r) for r in ("I", "IV", "VI", "XIV", "XVI", "xl")] == [1, 4, 6, 14, 16, 40]
    assert romano_para_arabico("IIII") is None and romano_para_arabico("abc") is None


def test_inciso_tse_vira_arabico_e_tres_mantem_a_forma():
    assert normalizar_inciso("VI") == "6"
    assert normalizar_inciso("inciso XIV") == "14"
    assert normalizar_inciso("6") == "6"
    assert normalizar_inciso("vi", "tres") == "VI"
    assert normalizar_inciso("14", "tres") == "14"
    assert inciso_alternativo(Filtros(texto="x", tribunais=["TRE-RS"], inciso="VI")) == "6"
    assert inciso_alternativo(Filtros(texto="x", tribunais=["TRE-RS"], inciso="14")) == "XIV"
    assert inciso_alternativo(Filtros(texto="x", inciso="VI")) is None


def test_leis_com_grafia_do_indice():
    # R1-05 e R1-06 da bateria: "VI"/"I" voltavam vazios no TSE; "6"/"1" trazem 423 e 349 decisões.
    p = parametros(Filtros(lei_numero="9504", artigo="73", inciso="VI", alinea="b"))
    assert p["leis"] == "_9504__Art._73_Par.__Inc._6_Let._b_"
    p = parametros(Filtros(lei_numero="9504", artigo="41-A"))
    assert p["leis"] == "_9504__Art._41A_Par.__Inc.__Let.__"
    p = parametros(Filtros(tribunais=["TRE-PE"], lei_numero="64", lei_ano="1990", artigo="1º", inciso="I", alinea='"g"'))
    assert p["leis"] == "_64_1990_Art._1_Par.__Inc._I_Let._g_"


def test_numero_processo_so_digitos():
    assert normalizar_numero_processo("0600752-54.2020.6.19.0172") == "06007525420206190172"
    assert parametros(Filtros(numero_processo="0600752-54"))["numero"] == "060075254"
    with pytest.raises(FiltroInvalido):
        parametros(Filtros(numero_processo="abc"))


def test_alinea_e_partes():
    assert normalizar_alinea('alínea "b"') == "b"
    assert normalizar_partes("Partido Socialista Brasileiro") == '"Partido Socialista Brasileiro"'
    assert normalizar_partes("PSB") == "PSB"
    assert normalizar_partes('"PSB" OU "Partido Socialista Brasileiro"') == '"PSB" OU "Partido Socialista Brasileiro"'


def test_zero_resultados_aponta_filtros():
    texto = lista_resultados({"totalRegistros": 0}, [], 1, 10, False, False,
                             filtros=Filtros(texto="abuso", classes=["XYZ"], lei_numero="9504", artigo="41-A"))
    assert "tse_listar_valores('classes', tribunal='TSE')" in texto
    assert "art. 41A" in texto
    assert lista_resultados({"totalRegistros": 0}, [], 1, 10, False, False).startswith("Nenhuma decisão encontrada.")
