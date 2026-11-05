"""Teste de ponta a ponta: sobe o servidor por stdio, como o Claude Desktop, e chama cada ferramenta.

Abre uma janela do navegador para a pesquisa. Uso:
    .venv\\Scripts\\python scripts\\testar_mcp.py
"""

import asyncio
import re
import sys

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _texto(resultado) -> str:
    return "\n".join(getattr(c, "text", "") for c in resultado.content)


async def _chamar(sessao: ClientSession, nome: str, argumentos: dict, limite: int = 1500) -> str:
    print(f"\n=== {nome} {argumentos}")
    texto = _texto(await sessao.call_tool(nome, argumentos))
    print(texto[:limite] + (" […]" if len(texto) > limite else ""))
    return texto


async def main() -> None:
    parametros = StdioServerParameters(command=sys.executable, args=["-m", "jurisprudencia_tse"])
    async with stdio_client(parametros) as (leitura, escrita):
        async with ClientSession(leitura, escrita) as sessao:
            await sessao.initialize()
            ferramentas = await sessao.list_tools()
            print("Ferramentas:", [f.name for f in ferramentas.tools])

            await _chamar(sessao, "tse_listar_valores", {"tipo": "classes", "filtro": "especial"}, 600)
            lista = await _chamar(
                sessao,
                "tse_pesquisar",
                {"texto": "abuso de poder econômico", "classes": ["REspEl"], "anos_eleicao": ["2024"],
                 "incluir_facetas": True},
                2500,
            )
            codigos = re.findall(r"codigoDecisao (\d+)", lista)
            if not codigos:
                print("\nSem codigoDecisao na resposta; encerrando.")
                return
            codigo = int(codigos[0])
            await _chamar(sessao, "tse_obter_decisao", {"codigo_decisao": codigo}, 1200)
            await _chamar(sessao, "tse_citacao", {"codigo_decisao": codigo})
            await _chamar(sessao, "tse_inteiro_teor", {"codigo_decisao": codigo, "tamanho": 2000}, 1200)
            await _chamar(sessao, "tse_pesquisar", {"texto": "abuso de poder econômico", "classes": ["REspEl"],
                                                    "anos_eleicao": ["2024"], "pagina": 2}, 400)


if __name__ == "__main__":
    asyncio.run(main())
