"""Servidor MCP: ferramentas de pesquisa, decisão, inteiro teor, citação e listas de valores do TSE."""

import logging
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from .citacao import cabecalho, citacao_abnt, link_andamento, link_decisao
from .consulta import Filtros, FiltroInvalido, rota
from .decisoes import CacheDecisoes, normalizar
from .formatacao import decisao_completa, lista_resultados
from .navegador import CaptchaPendente, ErroPortal, NavegadorTSE
from .servicos import ErroServico, ServicosTSE, texto_do_pdf

INSTRUCOES = """\
Pesquisa de jurisprudência no portal do Tribunal Superior Eleitoral (jurisprudencia.tse.jus.br).

Fluxo recomendado, do mais barato ao mais caro:
1. tse_pesquisar: lista com metadados e início da ementa. Ajuste filtros antes de paginar.
2. tse_obter_decisao: ementa e decisão completas, partes, legislação, súmulas e precedentes.
   Decisões já vistas numa pesquisa vêm do cache local, sem nova busca.
3. tse_inteiro_teor: texto do acórdão em PDF, por trechos. Use só quando a ementa não bastar.

A pesquisa roda no próprio portal, numa janela do Edge aberta pelo MCP e mantida fora da
tela, e passa pelo hCaptcha do TSE. A janela só aparece quando há desafio a resolver.
Se a ferramenta informar captcha pendente, peça ao usuário que resolva o desafio na
janela do navegador e só então repita a mesma chamada. Não repita a chamada
sem o usuário confirmar: tentativas seguidas aumentam os desafios.

Ao citar uma decisão, use tse_citacao ou informe classe, número, UF, relator, data de
julgamento e fonte e data de publicação. O codigoDecisao identifica a decisão no portal.
"""

logging.getLogger("httpx").setLevel(logging.WARNING)

_navegador = NavegadorTSE()
_servicos = ServicosTSE()
_cache = CacheDecisoes()


@asynccontextmanager
async def _ciclo_de_vida(_servidor):
    try:
        yield {}
    finally:
        await _navegador.fechar()
        await _servicos.fechar()


servidor = MCPServer(
    name="jurisprudencia-tse",
    title="Jurisprudência do TSE",
    instructions=INSTRUCOES,
    lifespan=_ciclo_de_vida,
)

_LEITURA = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

_MSG_CAPTCHA = (
    "CAPTCHA PENDENTE. O portal do TSE {situacao} e a pesquisa não foi enviada. "
    "A janela do Edge com o portal jurisprudencia.tse.jus.br, que normalmente fica escondida, foi "
    "trazida para a frente. Peça ao usuário para {acao} nessa janela e avisar quando terminar. Depois, "
    "repita esta mesma chamada; a página será recarregada e a janela volta a se esconder. "
    "Não repita antes da confirmação do usuário."
)


def _mensagem_captcha(erro: CaptchaPendente) -> str:
    if erro.desafio_visivel:
        return _MSG_CAPTCHA.format(situacao="exibiu um desafio hCaptcha", acao="resolver o desafio")
    return _MSG_CAPTCHA.format(
        situacao="não conseguiu validar o hCaptcha a tempo",
        acao="verificar se há um desafio a resolver",
    )


async def _executar_pesquisa(filtros: Filtros) -> tuple[dict, list[dict]]:
    resposta = await _navegador.pesquisar(rota(filtros))
    decisoes = [normalizar(bruta) for bruta in resposta.get("content") or []]
    for decisao in decisoes:
        _cache.guardar(decisao)
    return resposta, decisoes


@servidor.tool(title="Pesquisar jurisprudência do TSE", annotations=_LEITURA)
async def tse_pesquisar(
    texto: Annotated[str | None, Field(description=(
        "Pesquisa livre em todos os campos (sintaxe do portal: E, OU, NÃO, \"frase exata\", "
        "curinga *, proximidade \"termo1 termo2\"~5). Ex.: 'abuso de poder econômico E gravidade'."
    ))] = None,
    incluir_inteiro_teor: Annotated[bool, Field(description="Busca o texto também no inteiro teor dos acórdãos.")] = False,
    sinonimos: Annotated[bool, Field(description="Expande a pesquisa livre com sinônimos.")] = False,
    numero_processo: Annotated[str | None, Field(description="Nº do processo, da decisão, número único (NPU) ou protocolo.")] = None,
    relatores: Annotated[list[str] | None, Field(description="Nomes de relatores como em tse_listar_valores('relatores'). Combinados com OU.")] = None,
    classes: Annotated[list[str] | None, Field(description="Siglas de classe como em tse_listar_valores('classes'), ex.: ['REspEl', 'AREspEl', 'RO-El'].")] = None,
    anos_eleicao: Annotated[list[str] | None, Field(description="Anos de eleição, ex.: ['2024', '2020'].")] = None,
    ementa_decisao: Annotated[str | None, Field(description="Termos buscados só na ementa, na decisão e na indexação.")] = None,
    partes: Annotated[str | None, Field(description="Nome de parte.")] = None,
    uf: Annotated[str | None, Field(description="UF de origem, ex.: 'PE'.")] = None,
    data_inicio: Annotated[str | None, Field(description="Data inicial dd/mm/aaaa.")] = None,
    data_fim: Annotated[str | None, Field(description="Data final dd/mm/aaaa.")] = None,
    tipo_data: Annotated[Literal["julgamento", "publicacao"], Field(description="A que data se aplica o intervalo.")] = "julgamento",
    lei_numero: Annotated[str | None, Field(description="Número da norma citada na decisão, ex.: '9504' (Lei das Eleições), '64' (LC 64/90), '4737' (Código Eleitoral).")] = None,
    lei_ano: Annotated[str | None, Field(description="Ano da norma, ex.: '1997'.")] = None,
    artigo: Annotated[str | None, Field(description="Artigo da norma, ex.: '73'.")] = None,
    paragrafo: Annotated[str | None, Field(description="Parágrafo, ex.: '10'.")] = None,
    inciso: Annotated[str | None, Field(description="Inciso, em romanos como no índice do TSE, ex.: 'IV'.")] = None,
    alinea: Annotated[str | None, Field(description="Alínea, ex.: 'd'.")] = None,
    tipos_decisao: Annotated[
        list[Literal["Acórdão", "Decisão monocrática", "Sentença", "Resolução", "Decisão sem resolução"]] | None,
        Field(description="Padrão do portal: Acórdão, Resolução e Decisão sem resolução."),
    ] = None,
    ordenacao: Annotated[
        Literal["relevancia", "julgamento_recentes", "julgamento_antigas", "publicacao_recentes", "publicacao_antigas"],
        Field(description="Ordem dos resultados."),
    ] = "julgamento_recentes",
    pagina: Annotated[int, Field(ge=1, description="Página, a partir de 1.")] = 1,
    por_pagina: Annotated[Literal[10, 25, 50, 100], Field(description="Resultados por página. Cada página passa pelo captcha: prefira páginas maiores a paginar muito.")] = 10,
    ementa_completa: Annotated[bool, Field(description="Mostra a ementa inteira de cada resultado em vez do início.")] = False,
    incluir_facetas: Annotated[bool, Field(description="Inclui a distribuição dos resultados por classe, relator, eleição, assunto e UF.")] = False,
) -> str:
    """Pesquisa decisões no portal de jurisprudência do TSE (pesquisa avançada completa).

    Devolve total, página e, para cada decisão, identificação, codigoDecisao, relator, datas,
    disponibilidade do inteiro teor e a ementa (resumida ou completa).
    """
    filtros = Filtros(
        texto=texto,
        incluir_inteiro_teor=incluir_inteiro_teor,
        sinonimos=sinonimos,
        numero_processo=numero_processo,
        relatores=relatores or [],
        classes=classes or [],
        anos_eleicao=anos_eleicao or [],
        ementa_decisao=ementa_decisao,
        partes=partes,
        uf=uf,
        data_inicio=data_inicio,
        data_fim=data_fim,
        tipo_data=tipo_data,
        lei_numero=lei_numero,
        lei_ano=lei_ano,
        artigo=artigo,
        paragrafo=paragrafo,
        inciso=inciso,
        alinea=alinea,
        ordenacao=ordenacao,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    if tipos_decisao:
        filtros.tipos_decisao = list(tipos_decisao)
    try:
        resposta, decisoes = await _executar_pesquisa(filtros)
    except FiltroInvalido as erro:
        return f"Filtro inválido: {erro}"
    except CaptchaPendente as erro:
        return _mensagem_captcha(erro)
    except ErroPortal as erro:
        return f"Falha ao pesquisar no portal do TSE: {erro} Tente novamente em instantes."
    return lista_resultados(resposta, decisoes, pagina, por_pagina, ementa_completa, incluir_facetas)


async def _decisao(codigo: int) -> dict | str:
    if decisao := _cache.obter(codigo):
        return decisao
    try:
        _, decisoes = await _executar_pesquisa(Filtros(codigo_decisao=codigo, por_pagina=10))
    except CaptchaPendente as erro:
        return _mensagem_captcha(erro)
    except ErroPortal as erro:
        return f"Falha ao consultar o portal do TSE: {erro}"
    for decisao in decisoes:
        if int(decisao["codigoDecisao"]) == int(codigo):
            return decisao
    return f"Nenhuma decisão com codigoDecisao {codigo} no portal do TSE."


@servidor.tool(title="Obter decisão do TSE", annotations=_LEITURA)
async def tse_obter_decisao(
    codigo_decisao: Annotated[int, Field(description="codigoDecisao informado por tse_pesquisar ou presente no link do portal (?codigoDecisao=...).")],
) -> str:
    """Ementa e decisão completas de um julgado, com partes, legislação, súmulas, precedentes e citação."""
    decisao = await _decisao(codigo_decisao)
    return decisao if isinstance(decisao, str) else decisao_completa(decisao)


@servidor.tool(title="Ler inteiro teor (PDF)", annotations=_LEITURA)
async def tse_inteiro_teor(
    codigo_decisao: Annotated[int, Field(description="codigoDecisao da decisão.")],
    inicio: Annotated[int, Field(ge=0, description="Posição do primeiro caractere do trecho.")] = 0,
    tamanho: Annotated[int, Field(ge=1000, le=60000, description="Quantidade de caracteres do trecho.")] = 20000,
) -> str:
    """Baixa o inteiro teor em PDF do portal do TSE e devolve o texto, em trechos.

    O PDF fica salvo localmente; chamadas seguintes sobre a mesma decisão não baixam de novo.
    O TSE limita downloads seguidos: o MCP espaça as chamadas e pode demorar alguns segundos.
    """
    decisao = _cache.obter(codigo_decisao)
    if decisao is not None and not decisao.get("temInteiroTeorPDF"):
        return "O portal não disponibiliza inteiro teor em PDF para esta decisão."
    try:
        arquivo = await _servicos.baixar_inteiro_teor(codigo_decisao)
    except ErroServico as erro:
        return f"Não foi possível obter o inteiro teor: {erro}"
    texto = texto_do_pdf(arquivo)
    trecho = texto[inicio : inicio + tamanho]
    fim = inicio + len(trecho)
    if not trecho.strip():
        return f"PDF salvo em {arquivo}, mas sem texto extraível (provavelmente digitalizado)."
    rodape = f"\n\n[Caracteres {inicio}–{fim} de {len(texto)}. Arquivo: {arquivo}]"
    if fim < len(texto):
        rodape += f"\n[Continua: chame novamente com inicio={fim}]"
    return trecho + rodape


@servidor.tool(title="Citação de decisão do TSE", annotations=_LEITURA)
async def tse_citacao(
    codigo_decisao: Annotated[int, Field(description="codigoDecisao da decisão.")],
) -> str:
    """Citação ABNT no formato do botão "Copiar citação" do portal, cabeçalho de referência e links."""
    decisao = await _decisao(codigo_decisao)
    if isinstance(decisao, str):
        return decisao
    linhas = [
        f"Citação ABNT: {citacao_abnt(decisao)}",
        f"Cabeçalho (formato das cópias de ementa do portal): {cabecalho(decisao)}",
        f"Link da decisão: {link_decisao(decisao['codigoDecisao'])}",
    ]
    if andamento := link_andamento(decisao):
        linhas.append(f"Andamento processual: {andamento}")
    return "\n".join(linhas)


@servidor.tool(title="Valores válidos para filtros", annotations=_LEITURA)
async def tse_listar_valores(
    tipo: Annotated[Literal["classes", "relatores", "eleicoes", "normas"], Field(description="Lista desejada.")],
    filtro: Annotated[str | None, Field(description="Trecho para filtrar a lista, sem diferenciar maiúsculas.")] = None,
) -> str:
    """Valores aceitos pelos filtros de tse_pesquisar (classes, relatores, anos de eleição, normas)."""
    try:
        valores = await _servicos.listar(tipo)
    except Exception as erro:  # a lista é auxiliar; qualquer falha vira mensagem
        return f"Não foi possível obter a lista: {erro}"
    linhas = []
    for valor in valores:
        if tipo == "classes":
            linha = f"{valor.get('siglaClasse')} — {(valor.get('descricaoClasse') or '').strip()}"
        elif tipo == "normas":
            linha = f"{valor.get('sigla')}: {valor.get('tipo')} {valor.get('numero')}/{valor.get('ano')} — {valor.get('norma')}"
        else:
            linha = str(valor)
        if not filtro or filtro.lower() in linha.lower():
            linhas.append(linha)
    if not linhas:
        return "Nenhum valor corresponde ao filtro."
    return f"{len(linhas)} valores:\n" + "\n".join(linhas)


def main() -> None:
    servidor.run()


if __name__ == "__main__":
    main()
