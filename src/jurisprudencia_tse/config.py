"""Endereços do portal e pastas locais. As pastas podem ser trocadas por variáveis de ambiente."""

import os
from pathlib import Path

URL_PORTAL = "https://jurisprudencia.tse.jus.br/"
ROTA_PESQUISA = "#/jurisprudencia/pesquisa"
URL_API_PESQUISA = "https://sjur-pesquisa-api.tse.jus.br/tse/sjur-pesquisa-backend/rest/public/pesquisa"
URL_SERVICOS = "https://sjur-servicos.tse.jus.br/sjur-servicos/rest/"


def _pasta_padrao() -> Path:
    base = os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share")
    return Path(base) / "jurisprudencia-tse"


PASTA_DADOS = Path(os.environ.get("TSE_PASTA_DADOS") or _pasta_padrao())
PASTA_INTEIRO_TEOR = Path(os.environ.get("TSE_PASTA_INTEIRO_TEOR") or PASTA_DADOS / "inteiro-teor")
PASTA_DECISOES = PASTA_DADOS / "decisoes"
PASTA_PERFIL_NAVEGADOR = PASTA_DADOS / "perfil-navegador"

# Canal do Playwright: "msedge" (presente em todo Windows 11) ou "chrome".
NAVEGADOR = os.environ.get("TSE_NAVEGADOR", "msedge")

# "oculta": a janela fica fora da tela e da barra de tarefas e só aparece quando o hCaptcha exige
# desafio. "minimizada": idem, mas minimizada (com ícone na barra). "visivel": sempre à vista.
# (Navegador sem janela não funciona: o portal bloqueia com 403.)
JANELA = os.environ.get("TSE_JANELA", "oculta").strip().lower()
# A extensão do Claude Desktop (.mcpb) passa a opção como booleano: "true" = janela visível.
JANELA = {"true": "visivel", "false": "oculta", "visível": "visivel"}.get(JANELA, JANELA)

# O portal desiste do captcha após 15 s; damos margem para a resposta chegar.
TEMPO_MAXIMO_PESQUISA = float(os.environ.get("TSE_TEMPO_MAXIMO_PESQUISA", "40"))

# Intervalo mínimo entre downloads de inteiro teor. O servidor do TSE recusa chamadas seguidas.
INTERVALO_DOWNLOADS = float(os.environ.get("TSE_INTERVALO_DOWNLOADS", "10"))
ESPERA_APOS_LIMITE = float(os.environ.get("TSE_ESPERA_APOS_LIMITE", "45"))

USER_AGENT = "jurisprudencia-tse-mcp/0.1 (+https://github.com/luisguilhermeverissimo-hue/jurisprudencia-tse)"
