"""Bateria de medição: conversa com o servidor MCP por stdio, como o Claude, e mede cada chamada.

Lê os casos de testes/casos.json, chama as ferramentas em série e grava:
- testes/metricas-<versão>-<data>.jsonl: uma linha por chamada (tempo, caracteres, tokens,
  total de resultados, devolvidos, captcha, erro, cache);
- testes/respostas/<id>.txt: o texto devolvido pela ferramenta (para avaliar a pertinência);
- testes/resumo-<versão>.md: tabelas por ferramenta e por tipo de tempo, e as comparações de custo.

Captcha: quando a ferramenta devolve captcha pendente, o script grava a ocorrência, deixa o
servidor (e a janela do Edge) de pé e espera o arquivo testes/.continuar. Crie o arquivo depois
que o desafio for resolvido e o mesmo caso é repetido. Se o conteúdo do arquivo for "parar", o
script encerra; numa nova execução, os casos já medidos ficam de fora (use --refazer para medir
de novo).

Tokens: com ANTHROPIC_API_KEY, conta pelo endpoint /v1/messages/count_tokens; sem a chave,
estima por caracteres ÷ 3,5.

O servidor usa uma pasta de dados própria (testes/dados, ou TSE_PASTA_DADOS se já definida),
para não disputar o perfil do Edge com a extensão do Claude Desktop.

Uso:
    .venv\\Scripts\\python scripts\\medir_bateria.py --rodada 1
    .venv\\Scripts\\python scripts\\medir_bateria.py --ids R1-01,R1-02 --pausa 20
    .venv\\Scripts\\python scripts\\medir_bateria.py --so-inicio 3      (só o tempo de initialize)
    .venv\\Scripts\\python scripts\\medir_bateria.py --resumo            (só refaz o resumo)
"""

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import statistics
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

RAIZ = Path(__file__).resolve().parent.parent
PASTA_TESTES = RAIZ / "testes"
PASTA_RESPOSTAS = PASTA_TESTES / "respostas"
ARQUIVO_CONTINUAR = PASTA_TESTES / ".continuar"
CARACTERES_POR_TOKEN = 3.5

FERRAMENTAS_NAVEGADOR = {"tse_pesquisar", "tse_obter_decisao", "tse_citacao"}
PREFIXOS_ERRO = (
    "Filtro inválido",
    "Falha ao",
    "Não foi possível",
    "Nenhuma decisão com codigoDecisao",
    "O portal não disponibiliza",
)
RE_TOTAL = re.compile(r"^(\d+) decisões encontradas\. Página (\d+) de (\d+) \((\d+) nesta página\)")
RE_RESULTADO = re.compile(r"^### (\d+)\. (.*?) \[codigoDecisao (\d+)\]", re.M)


def _versao_pacote() -> str:
    try:
        return version("jurisprudencia-tse")
    except PackageNotFoundError:
        texto = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
        return re.search(r'^version = "([^"]+)"', texto, re.M).group(1)


def _agora() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- tokens

class ContadorTokens:
    """Conta pelo endpoint gratuito da API quando há chave; senão, estima por caracteres."""

    def __init__(self, modelo: str):
        self.chave = os.environ.get("ANTHROPIC_API_KEY")
        self.modelo = modelo
        self._base: int | None = None
        self._cliente = None
        if self.chave:
            import httpx

            self._cliente = httpx.Client(timeout=30)

    @property
    def metodo(self) -> str:
        return f"count_tokens:{self.modelo}" if self.chave else f"estimativa:caracteres/{CARACTERES_POR_TOKEN}"

    def _contar_api(self, texto: str) -> int:
        resposta = self._cliente.post(
            "https://api.anthropic.com/v1/messages/count_tokens",
            headers={"x-api-key": self.chave, "anthropic-version": "2023-06-01"},
            json={"model": self.modelo, "messages": [{"role": "user", "content": texto}]},
        )
        resposta.raise_for_status()
        return int(resposta.json()["input_tokens"])

    def contar(self, texto: str) -> tuple[int, str]:
        if self.chave:
            try:
                if self._base is None:  # custo fixo da mensagem, descontado de cada contagem
                    self._base = self._contar_api(".") - 1
                return max(self._contar_api(texto) - self._base, 0), self.metodo
            except Exception as erro:  # noqa: BLE001 - sem a API, cai na estimativa
                print(f"  (count_tokens falhou: {erro}; usando estimativa)", flush=True)
        return round(len(texto) / CARACTERES_POR_TOKEN), f"estimativa:caracteres/{CARACTERES_POR_TOKEN}"


# --------------------------------------------------------------------------- casos e referências

class ReferenciaNaoResolvida(Exception):
    pass


def _resposta_salva(caso_id: str) -> str:
    arquivo = PASTA_RESPOSTAS / f"{caso_id}.txt"
    if not arquivo.exists():
        raise ReferenciaNaoResolvida(f"o caso {caso_id} ainda não tem resposta gravada")
    return arquivo.read_text(encoding="utf-8")


def _resultado(caso_id: str, posicao: int) -> re.Match:
    resultados = list(RE_RESULTADO.finditer(_resposta_salva(caso_id)))
    if len(resultados) < posicao:
        raise ReferenciaNaoResolvida(f"o caso {caso_id} tem {len(resultados)} resultados, pedido o {posicao}º")
    return resultados[posicao - 1]


def resolver(valor):
    """Troca {"$codigo": [id, n]}, {"$numero": [id, n]} e {"$npu": id} por valores de respostas anteriores."""
    if isinstance(valor, list):
        return [resolver(v) for v in valor]
    if not isinstance(valor, dict):
        return valor
    if "$codigo" in valor:
        caso_id, posicao = valor["$codigo"]
        return int(_resultado(caso_id, int(posicao)).group(3))
    if "$numero" in valor:
        caso_id, posicao = valor["$numero"]
        identificacao = _resultado(caso_id, int(posicao)).group(2)
        achado = re.search(r"nº ([^\s/]+)", identificacao)
        if not achado or achado.group(1) == "?":
            raise ReferenciaNaoResolvida(f"sem número de processo em {identificacao!r}")
        return achado.group(1)
    if "$npu" in valor:
        achado = re.search(r"^Número único: (.+)$", _resposta_salva(valor["$npu"]), re.M)
        if not achado:
            raise ReferenciaNaoResolvida(f"sem 'Número único' na resposta de {valor['$npu']}")
        return achado.group(1).strip()
    return {chave: resolver(v) for chave, v in valor.items()}


def carregar_casos(arquivo: Path) -> list[dict]:
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    return dados["casos"] if isinstance(dados, dict) else dados


# --------------------------------------------------------------------------- análise da resposta

def _portal(ferramenta: str, argumentos: dict) -> str | None:
    if ferramenta == "tse_pesquisar":
        tribunais = [str(t).upper() for t in argumentos.get("tribunais") or []]
        return "tres" if any(t != "TSE" for t in tribunais) else "tse"
    if ferramenta in ("tse_obter_decisao", "tse_citacao"):
        tribunal = (argumentos.get("tribunal") or "").upper()
        return "tres" if tribunal.startswith("TRE") else ("tse" if tribunal == "TSE" else "tse+tres?")
    return None


def analisar(texto: str, is_error: bool) -> dict:
    info = {"captcha": texto.startswith("CAPTCHA PENDENTE"), "erro": bool(is_error), "mensagem_erro": None,
            "total_resultados": None, "devolvidos": None}
    if info["captcha"]:
        return info
    if is_error or texto.startswith(PREFIXOS_ERRO):
        info["erro"] = True
        info["mensagem_erro"] = texto[:300]
    if achado := RE_TOTAL.match(texto):
        info["total_resultados"] = int(achado.group(1))
        info["devolvidos"] = int(achado.group(4))
    elif texto.startswith("Nenhuma decisão encontrada"):
        info["total_resultados"] = 0
        info["devolvidos"] = 0
    return info


# --------------------------------------------------------------------------- execução

class Bateria:
    def __init__(self, args, pasta_dados: Path, versao: str):
        self.args = args
        self.pasta_dados = pasta_dados
        self.versao = versao
        self.tokens = ContadorTokens(args.modelo_tokens)
        self.saida = PASTA_TESTES / f"metricas-{versao}-{dt.date.today().isoformat()}.jsonl"
        self.execucao = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.navegador_ativo = False
        self.portais_vistos: set[str] = set()
        self.ultima_navegacao = 0.0

    def gravar(self, registro: dict) -> None:
        registro = {"execucao": self.execucao, "versao": self.versao, "quando": _agora(), **registro}
        with self.saida.open("a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")

    def parametros(self) -> StdioServerParameters:
        ambiente = dict(os.environ)
        ambiente["TSE_PASTA_DADOS"] = str(self.pasta_dados)
        ambiente.setdefault("PYTHONIOENCODING", "utf-8")
        if self.args.lancador:
            return StdioServerParameters(command="uv", args=["run", str(RAIZ / "mcpb" / "lancador.py")],
                                         env=ambiente, cwd=str(RAIZ))
        exe = RAIZ / ".venv" / "Scripts" / "jurisprudencia-tse.exe"
        if exe.exists():
            return StdioServerParameters(command=str(exe), env=ambiente, cwd=str(RAIZ))
        return StdioServerParameters(command=sys.executable, args=["-m", "jurisprudencia_tse.servidor"],
                                     env=ambiente, cwd=str(RAIZ))

    def _cache(self, ferramenta: str, argumentos: dict) -> bool | None:
        codigo = argumentos.get("codigo_decisao")
        if codigo is None:
            return None
        if ferramenta == "tse_inteiro_teor":
            return any((self.pasta_dados / "inteiro-teor").glob(f"{int(codigo)}_*.pdf"))
        if ferramenta in ("tse_obter_decisao", "tse_citacao"):
            return (self.pasta_dados / "decisoes" / f"{int(codigo)}.json").exists()
        return None

    def _tipo_tempo(self, ferramenta: str, portal: str | None, cache: bool | None, texto: str) -> str:
        if ferramenta == "tse_listar_valores":
            return "lista"
        if ferramenta == "tse_inteiro_teor":
            return "inteiro_teor_cache" if cache else "inteiro_teor"
        if cache:
            return "cache"
        if texto.startswith("Filtro inválido"):
            return "validacao"
        if not self.navegador_ativo:
            return "frio"
        if portal not in self.portais_vistos:
            return "primeira_portal"
        return "seguinte"

    async def _esperar_continuar(self, caso_id: str) -> bool:
        print(f"\n>>> CAPTCHA PENDENTE no caso {caso_id}. Resolva o desafio na janela do Edge e crie "
              f"{ARQUIVO_CONTINUAR} (conteúdo 'parar' encerra).", flush=True)
        limite = time.monotonic() + self.args.espera_captcha
        while time.monotonic() < limite:
            if ARQUIVO_CONTINUAR.exists():
                conteudo = ARQUIVO_CONTINUAR.read_text(encoding="utf-8", errors="ignore").strip().lower()
                ARQUIVO_CONTINUAR.unlink()
                if conteudo == "parar":
                    print(">>> Pedido de parada recebido.", flush=True)
                    return False
                print(f">>> Continuando: repetindo o caso {caso_id}.", flush=True)
                return True
            await asyncio.sleep(2)
        print(">>> Tempo de espera do captcha esgotado.", flush=True)
        return False

    async def chamar(self, sessao: ClientSession, caso: dict) -> str:
        """Executa um caso; devolve 'ok', 'captcha' ou 'parar'."""
        ferramenta = caso["ferramenta"]
        base = {k: caso.get(k) for k in ("id", "rodada", "teste", "tema", "comparacao", "pedido")}
        base["ferramenta"] = ferramenta
        try:
            argumentos = resolver(caso.get("argumentos") or {})
            pre = resolver(caso.get("pre") or {})
        except ReferenciaNaoResolvida as erro:
            print(f"  [{caso['id']}] referência não resolvida: {erro}", flush=True)
            self.gravar({**base, "argumentos": caso.get("argumentos"), "erro": True,
                         "mensagem_erro": f"referência não resolvida: {erro}", "nao_executado": True})
            return "ok"
        if codigo := pre.get("apagar_cache"):
            (self.pasta_dados / "decisoes" / f"{int(codigo)}.json").unlink(missing_ok=True)

        portal = _portal(ferramenta, argumentos)
        cache = self._cache(ferramenta, argumentos)
        usa_navegador = ferramenta in FERRAMENTAS_NAVEGADOR and not cache
        if usa_navegador and self.ultima_navegacao:
            espera = self.args.pausa - (time.monotonic() - self.ultima_navegacao)
            if espera > 0:
                print(f"  (pausa de {espera:.0f} s)", flush=True)
                await asyncio.sleep(espera)

        print(f"[{caso['id']}] {ferramenta} {json.dumps(argumentos, ensure_ascii=False)}", flush=True)
        inicio = time.perf_counter()
        excecao = None
        try:
            resultado = await sessao.call_tool(ferramenta, argumentos)
            texto = "\n".join(getattr(c, "text", "") for c in resultado.content)
            is_error = bool(getattr(resultado, "is_error", False) or getattr(resultado, "isError", False))
        except Exception as erro:  # noqa: BLE001 - registra e segue
            texto, is_error, excecao = f"EXCEÇÃO NO CLIENTE: {erro!r}", True, repr(erro)
        segundos = time.perf_counter() - inicio
        if usa_navegador:
            self.ultima_navegacao = time.monotonic()

        info = analisar(texto, is_error)
        tipo_tempo = self._tipo_tempo(ferramenta, portal, cache, texto)
        if usa_navegador and tipo_tempo != "validacao":
            self.navegador_ativo = True
            if portal in ("tse", "tres"):
                self.portais_vistos.add(portal)
        tokens, metodo = self.tokens.contar(texto)
        registro = {
            **base,
            "argumentos": argumentos,
            "segundos": round(segundos, 2),
            "tipo_tempo": tipo_tempo,
            "portal": portal,
            "cache": cache,
            "caracteres": len(texto),
            "tokens": tokens,
            "tokens_metodo": metodo,
            **info,
            "tokens_por_resultado": round(tokens / info["devolvidos"]) if info["devolvidos"] else None,
            "excecao": excecao,
            "inicio_resposta": texto[:200],
        }
        if not info["captcha"]:
            PASTA_RESPOSTAS.mkdir(parents=True, exist_ok=True)
            arquivo = PASTA_RESPOSTAS / f"{caso['id']}.txt"
            arquivo.write_text(texto, encoding="utf-8")
            registro["resposta_arquivo"] = str(arquivo.relative_to(RAIZ))
        self.gravar(registro)
        resumo = (f"  -> {segundos:.1f} s · {tipo_tempo} · {len(texto)} car. · {tokens} tok · "
                  f"total={info['total_resultados']} devolvidos={info['devolvidos']}")
        if info["captcha"]:
            resumo += " · CAPTCHA"
        if info["erro"]:
            resumo += f" · ERRO: {texto[:120]!r}"
        print(resumo, flush=True)
        return "captcha" if info["captcha"] else "ok"

    async def rodar(self, casos: list[dict]) -> int:
        print(f"Servidor: {' '.join([self.parametros().command, *self.parametros().args])}", flush=True)
        print(f"Dados: {self.pasta_dados} · Métricas: {self.saida} · Tokens: {self.tokens.metodo}", flush=True)
        with (PASTA_TESTES / "servidor.log").open("a", encoding="utf-8") as log:
            log.write(f"\n===== {self.execucao} =====\n")
            log.flush()
            inicio = time.perf_counter()
            async with stdio_client(self.parametros(), errlog=log) as (leitura, escrita):
                async with ClientSession(leitura, escrita) as sessao:
                    resultado = await sessao.initialize()
                    segundos = time.perf_counter() - inicio
                    info = getattr(resultado, "server_info", None)
                    self.gravar({"evento": "initialize", "segundos": round(segundos, 2),
                                 "lancador": bool(self.args.lancador),
                                 "servidor": getattr(info, "name", None),
                                 "versao_servidor": getattr(info, "version", None)})
                    print(f"initialize: {segundos:.2f} s ({getattr(info, 'name', '?')} "
                          f"{getattr(info, 'version', '?')})", flush=True)
                    if self.args.so_inicio:
                        return 0
                    for caso in casos:
                        while True:
                            estado = await self.chamar(sessao, caso)
                            if estado != "captcha":
                                break
                            if not await self._esperar_continuar(caso["id"]):
                                print(f"Parado no caso {caso['id']}. Rode de novo para retomar dele.", flush=True)
                                return 3
                    return 0


# --------------------------------------------------------------------------- resumo

def ler_registros(versao: str) -> list[dict]:
    registros = []
    for arquivo in sorted(PASTA_TESTES.glob(f"metricas-{versao}-*.jsonl")):
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                registros.append(json.loads(linha))
    return registros


def ids_concluidos(versao: str) -> set[str]:
    return {r["id"] for r in ler_registros(versao)
            if r.get("id") and not r.get("captcha") and not r.get("nao_executado")}


def _mediana(valores):
    valores = [v for v in valores if v is not None]
    return round(statistics.median(valores), 1) if valores else None


def _maximo(valores):
    valores = [v for v in valores if v is not None]
    return round(max(valores), 1) if valores else None


def _linha(*celulas) -> str:
    return "| " + " | ".join("—" if c is None else str(c) for c in celulas) + " |"


def gerar_resumo(versao: str) -> Path:
    registros = ler_registros(versao)
    chamadas = [r for r in registros if r.get("id")]
    inicios = [r for r in registros if r.get("evento") == "initialize"]
    # Para cada caso, vale a última medição sem captcha (as com captcha contam só na taxa).
    finais: dict[str, dict] = {}
    for r in chamadas:
        if not r.get("captcha") and not r.get("nao_executado"):
            finais[r["id"]] = r
    navegacoes = [r for r in chamadas if r.get("tipo_tempo") in ("frio", "primeira_portal", "seguinte")
                  or r.get("captcha")]
    captchas = sum(1 for r in chamadas if r.get("captcha"))

    linhas = [f"# Resumo da bateria — versão {versao}", "",
              f"Gerado em {_agora()}. {len(finais)} casos medidos, {len(chamadas)} chamadas no total "
              f"({captchas} com captcha em {len(navegacoes)} chamadas pelo navegador).", ""]
    metodos = sorted({r.get("tokens_metodo") for r in chamadas if r.get("tokens_metodo")})
    linhas += [f"Tokens: {', '.join(metodos) or '—'}.", ""]

    if inicios:
        tempos = [r["segundos"] for r in inicios]
        linhas += ["## Início do servidor (initialize)", "",
                   _linha("Execuções", "Mediana (s)", "Máximo (s)"), _linha("---", "---", "---"),
                   _linha(len(tempos), _mediana(tempos), _maximo(tempos)), ""]

    linhas += ["## Por ferramenta", "",
               _linha("Ferramenta", "Casos", "Tempo mediano (s)", "Tempo máx. (s)", "Tokens medianos",
                      "Tokens máx.", "Captcha", "Erros"),
               _linha(*["---"] * 8)]
    for ferramenta in sorted({r["ferramenta"] for r in chamadas}):
        todos = [r for r in chamadas if r["ferramenta"] == ferramenta]
        medidos = [r for r in finais.values() if r["ferramenta"] == ferramenta]
        nav = [r for r in todos if r.get("tipo_tempo") in ("frio", "primeira_portal", "seguinte") or r.get("captcha")]
        taxa = f"{sum(1 for r in todos if r.get('captcha'))}/{len(nav)}" if nav else "—"
        linhas.append(_linha(ferramenta, len(medidos), _mediana([r.get("segundos") for r in medidos]),
                             _maximo([r.get("segundos") for r in medidos]),
                             _mediana([r.get("tokens") for r in medidos]), _maximo([r.get("tokens") for r in medidos]),
                             taxa, sum(1 for r in medidos if r.get("erro"))))
    linhas.append("")

    rodadas = sorted({r.get("rodada") for r in finais.values() if r.get("rodada") is not None})
    if rodadas:
        linhas += ["## Por rodada", "",
                   _linha("Rodada", "Casos", "Pesquisas (navegador)", "Captcha", "Erros", "Tempo mediano das pesquisas (s)",
                          "Tokens medianos"),
                   _linha(*["---"] * 7)]
        for rodada in rodadas:
            medidos = [r for r in finais.values() if r.get("rodada") == rodada]
            todos = [r for r in chamadas if r.get("rodada") == rodada]
            nav = [r for r in todos if r.get("tipo_tempo") in ("frio", "primeira_portal", "seguinte") or r.get("captcha")]
            linhas.append(_linha(rodada, len(medidos), len(nav), sum(1 for r in todos if r.get("captcha")),
                                 sum(1 for r in medidos if r.get("erro")),
                                 _mediana([r["segundos"] for r in medidos
                                           if r.get("tipo_tempo") in ("frio", "primeira_portal", "seguinte")]),
                                 _mediana([r.get("tokens") for r in medidos])))
        linhas.append("")

    linhas += ["## Tempo por tipo de chamada", "",
               _linha("Tipo", "Chamadas", "Mediana (s)", "Máximo (s)"), _linha(*["---"] * 4)]
    for tipo in ("frio", "primeira_portal", "seguinte", "cache", "inteiro_teor", "inteiro_teor_cache", "lista", "validacao"):
        tempos = [r["segundos"] for r in finais.values() if r.get("tipo_tempo") == tipo]
        if tempos:
            linhas.append(_linha(tipo, len(tempos), _mediana(tempos), _maximo(tempos)))
    linhas.append("")

    comparacoes = sorted({r["comparacao"] for r in finais.values() if r.get("comparacao")})
    if comparacoes:
        linhas += ["## Comparações de custo", "",
                   _linha("Comparação", "Caso", "Argumento", "Caracteres", "Tokens", "Devolvidos", "Tokens/resultado"),
                   _linha(*["---"] * 7)]
        for comparacao in comparacoes:
            for r in (r for r in finais.values() if r.get("comparacao") == comparacao):
                argumento = r["argumentos"].get(comparacao.replace("inteiro_teor_", ""), r["argumentos"].get(comparacao))
                linhas.append(_linha(comparacao, r["id"], argumento, r.get("caracteres"), r.get("tokens"),
                                     r.get("devolvidos"), r.get("tokens_por_resultado")))
        linhas.append("")

    linhas += ["## Casos", "",
               _linha("Caso", "Ferramenta", "Tipo", "Tempo (s)", "Tokens", "Total", "Devolvidos", "Cache", "Erro"),
               _linha(*["---"] * 9)]
    for caso_id in sorted(finais):
        r = finais[caso_id]
        erro = (r.get("mensagem_erro") or "sim")[:80].replace("|", "/").replace("\n", " ") if r.get("erro") else ""
        linhas.append(_linha(caso_id, r["ferramenta"], r.get("tipo_tempo"), r.get("segundos"), r.get("tokens"),
                             r.get("total_resultados"), r.get("devolvidos"), r.get("cache"), erro))
    destino = PASTA_TESTES / f"resumo-{versao}.md"
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return destino


# --------------------------------------------------------------------------- linha de comando

def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--casos", type=Path, default=PASTA_TESTES / "casos.json")
    parser.add_argument("--rodada", type=int, help="Só os casos desta rodada.")
    parser.add_argument("--ids", help="Só estes casos, separados por vírgula (na ordem do arquivo).")
    parser.add_argument("--pausa", type=float, default=25.0, help="Segundos mínimos entre chamadas pelo navegador.")
    parser.add_argument("--refazer", action="store_true", help="Mede de novo casos já medidos.")
    parser.add_argument("--espera-captcha", type=float, default=1800.0, help="Segundos de espera pelo .continuar.")
    parser.add_argument("--lancador", action="store_true", help="Sobe o servidor pelo mcpb/lancador.py (uv).")
    parser.add_argument("--so-inicio", type=int, metavar="N", help="Só mede o initialize, N vezes.")
    parser.add_argument("--resumo", action="store_true", help="Só gera o resumo a partir dos JSONL.")
    parser.add_argument("--modelo-tokens", default=os.environ.get("TOKENS_MODELO", "claude-opus-5-5"))
    args = parser.parse_args()

    versao = _versao_pacote()
    PASTA_TESTES.mkdir(exist_ok=True)
    if args.resumo:
        print(gerar_resumo(versao))
        return 0
    pasta_dados = Path(os.environ.get("TSE_PASTA_DADOS") or PASTA_TESTES / "dados").resolve()
    bateria = Bateria(args, pasta_dados, versao)

    if args.so_inicio:
        for _ in range(args.so_inicio):
            asyncio.run(bateria.rodar([]))
        print(gerar_resumo(versao))
        return 0

    casos = carregar_casos(args.casos)
    if args.rodada is not None:
        casos = [c for c in casos if c.get("rodada") == args.rodada]
    if args.ids:
        pedidos = [i.strip() for i in args.ids.split(",") if i.strip()]
        desconhecidos = set(pedidos) - {c["id"] for c in casos}
        if desconhecidos:
            parser.error(f"casos desconhecidos: {sorted(desconhecidos)}")
        casos = [c for c in casos if c["id"] in pedidos]
    if not args.refazer:
        feitos = ids_concluidos(versao)
        pulados = [c["id"] for c in casos if c["id"] in feitos]
        if pulados:
            print(f"Já medidos (use --refazer para repetir): {', '.join(pulados)}", flush=True)
        casos = [c for c in casos if c["id"] not in feitos]
    if not casos:
        print("Nada a medir.")
        print(gerar_resumo(versao))
        return 0
    ARQUIVO_CONTINUAR.unlink(missing_ok=True)
    codigo = asyncio.run(bateria.rodar(casos))
    print(f"\nResumo: {gerar_resumo(versao)}", flush=True)
    print("FIM DA EXECUÇÃO" + (" (parada por captcha)" if codigo == 3 else ""), flush=True)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
