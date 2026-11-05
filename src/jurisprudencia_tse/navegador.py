"""Pesquisa pelo próprio portal, num navegador comum (janela fora da tela por padrão).

O endpoint de pesquisa exige um token hCaptcha gerado no navegador. Em vez de chamar a API
diretamente, o MCP abre o portal (Edge ou Chrome instalados, via Playwright), muda o endereço
da página para a pesquisa desejada e lê a resposta que o próprio portal recebe. O captcha roda
exatamente como numa pesquisa manual; quando o hCaptcha pede um desafio, quem resolve é o usuário,
na janela aberta.

Comportamento do portal verificado em 26/10/2026 (docs/MAPEAMENTO_API_PORTAL_TSE.md, seção 9.1):
- mudar o hash da página já carregada dispara a pesquisa; recarregar a página não dispara;
- sem token em 15 s, o portal desiste, registra "Timeout ao validar o hCaptcha." no console
  e a tela de resultados para de responder até a página ser recarregada.
"""

import asyncio
import shutil
import tempfile
from pathlib import Path

from playwright.async_api import Error as ErroPlaywright
from playwright.async_api import async_playwright

from .config import JANELA, NAVEGADOR, PASTA_PERFIL_NAVEGADOR, ROTA_PESQUISA, TEMPO_MAXIMO_PESQUISA, URL_PORTAL
from .janela_windows import mostrar_na_barra_de_tarefas

_SELETOR_PRONTO = 'button:has-text("Pesquisar")'

_LARGURA, _ALTURA = 1200, 900
# Posição longe de qualquer monitor. A janela existe e a página segue "visível" para o portal
# (relógios e animações em velocidade normal), mas não aparece na tela.
_FORA_DA_TELA = -20000
# Sem isto, o navegador desacelera a página que não está à vista e o hCaptcha pode passar dos
# 15 s que o portal espera, o que obrigava a mostrar a janela sem haver desafio.
_ARGUMENTOS_SEM_DESACELERAR = [
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
]
_MODOS_JANELA = ("oculta", "minimizada", "visivel")
_FALHAS_CAPTCHA = ("Timeout ao validar o hCaptcha", "Erro ao executar captcha", "Erro ao carregar o hCaptcha")

_JS_DESAFIO_VISIVEL = """
() => [...document.querySelectorAll('iframe')]
  .filter(f => (f.src || '').includes('hcaptcha') && (f.src || '').includes('frame=challenge'))
  .some(f => {
    const r = f.getBoundingClientRect();
    if (r.width < 100 || r.height < 100) return false;
    for (let e = f; e && e !== document.documentElement; e = e.parentElement) {
      const s = getComputedStyle(e);
      if (s.visibility === 'hidden' || s.display === 'none' || parseFloat(s.opacity) === 0) return false;
    }
    return true;
  })
"""


class CaptchaPendente(RuntimeError):
    def __init__(self, desafio_visivel: bool):
        self.desafio_visivel = desafio_visivel
        super().__init__("hCaptcha não validado")


class ErroPortal(RuntimeError):
    pass


def _e_resposta_de_pesquisa(resposta) -> bool:
    return resposta.url.endswith("/public/pesquisa") and resposta.request.method == "POST"


class NavegadorTSE:
    def __init__(self):
        self._playwright = None
        self._contexto = None
        self._pagina = None
        self._trava = asyncio.Lock()
        self._precisa_recarregar = False
        self._falha_captcha: str | None = None
        # "oculta": janela fora da tela e fora da barra de tarefas; "minimizada": janela minimizada;
        # "visivel": sempre à vista. Nos dois primeiros, ela só aparece quando o hCaptcha pede
        # desafio e some de novo depois da primeira pesquisa bem-sucedida. Navegador sem janela
        # (headless) não é opção: o portal responde 403 a ele.
        self._modo = JANELA if JANELA in _MODOS_JANELA else "oculta"
        self._janela_exibida = False
        self._perfil_temporario: Path | None = None

    async def _fechar_contexto(self) -> None:
        contexto, self._contexto, self._pagina = self._contexto, None, None
        if contexto is not None:
            try:
                await contexto.close()
            except ErroPlaywright:
                pass

    async def fechar(self) -> None:
        await self._fechar_contexto()
        if self._playwright is not None:
            await self._playwright.stop()
        self._playwright = None
        if self._perfil_temporario is not None:
            shutil.rmtree(self._perfil_temporario, ignore_errors=True)
            self._perfil_temporario = None

    def _ao_fechar_contexto(self, contexto) -> None:
        # O usuário fechou a janela: a próxima pesquisa abre outra.
        if contexto is self._contexto:
            self._contexto = self._pagina = None
            self._janela_exibida = False

    async def _definir_janela(self, *limites: dict) -> None:
        """Aplica, em ordem, estados e posições à janela pelo protocolo de depuração do navegador.

        O protocolo não aceita mudar o estado ("minimized") e a posição na mesma chamada.
        """
        try:
            cdp = await self._contexto.new_cdp_session(self._pagina)
            try:
                alvo = await cdp.send("Browser.getWindowForTarget")
                for bounds in limites:
                    await cdp.send("Browser.setWindowBounds", {"windowId": alvo["windowId"], "bounds": bounds})
            finally:
                await cdp.detach()
        except ErroPlaywright:
            pass

    async def _posicao_centralizada(self) -> dict:
        """Posição e tamanho que cabem na área útil da tela principal, com a janela centralizada."""
        try:
            esquerda, topo, largura, altura = await self._pagina.evaluate(
                "[screen.availLeft || 0, screen.availTop || 0, screen.availWidth, screen.availHeight]"
            )
        except ErroPlaywright:
            esquerda, topo, largura, altura = 0, 0, _LARGURA, _ALTURA
        w, h = min(_LARGURA, largura), min(_ALTURA, altura)
        return {"left": esquerda + (largura - w) // 2, "top": topo + (altura - h) // 2, "width": w, "height": h}

    async def estado_janela(self) -> str | None:
        try:
            cdp = await self._contexto.new_cdp_session(self._pagina)
            try:
                alvo = await cdp.send("Browser.getWindowForTarget")
                return alvo["bounds"]["windowState"]
            finally:
                await cdp.detach()
        except (ErroPlaywright, AttributeError):
            return None

    async def _exibir_janela(self) -> None:
        if self._modo == "oculta":
            mostrar_na_barra_de_tarefas(True)
            await self._definir_janela({"windowState": "normal"}, await self._posicao_centralizada())
        else:
            await self._definir_janela({"windowState": "normal"})
        await self._pagina.bring_to_front()
        self._janela_exibida = True

    async def _ocultar_janela(self) -> None:
        if self._modo == "visivel":
            return
        if self._modo == "oculta":
            fora = {"left": _FORA_DA_TELA, "top": _FORA_DA_TELA, "width": _LARGURA, "height": _ALTURA}
            await self._definir_janela({"windowState": "normal"}, fora)
            mostrar_na_barra_de_tarefas(False)
        else:
            await self._definir_janela({"windowState": "minimized"})
        self._janela_exibida = False

    def _ao_receber_console(self, mensagem) -> None:
        texto = mensagem.text
        if any(falha in texto for falha in _FALHAS_CAPTCHA):
            self._falha_captcha = texto

    async def _garantir_pagina(self) -> None:
        if self._pagina is not None and not self._pagina.is_closed():
            return
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        if self._contexto is None:
            self._contexto = await self._abrir_contexto()
            self._contexto.on("close", self._ao_fechar_contexto)
        paginas = self._contexto.pages
        self._pagina = paginas[0] if paginas else await self._contexto.new_page()
        self._pagina.on("console", self._ao_receber_console)
        await self._ocultar_janela()
        await self._pagina.goto(URL_PORTAL + ROTA_PESQUISA, wait_until="domcontentloaded")
        await self._aguardar_portal()

    async def _abrir_contexto(self):
        argumentos = [f"--window-size={_LARGURA},{_ALTURA}", *_ARGUMENTOS_SEM_DESACELERAR]
        if self._modo == "oculta":
            # Já nasce fora da tela, para não piscar.
            argumentos.append(f"--window-position={_FORA_DA_TELA},{_FORA_DA_TELA}")
        elif self._modo == "minimizada":
            argumentos.append("--start-minimized")
        opcoes = dict(channel=NAVEGADOR, headless=False, no_viewport=True, args=argumentos)
        if self._perfil_temporario is None:
            PASTA_PERFIL_NAVEGADOR.mkdir(parents=True, exist_ok=True)
            try:
                # Perfil próprio e persistente: o portal e o hCaptcha reconhecem a sessão entre usos.
                return await self._playwright.chromium.launch_persistent_context(str(PASTA_PERFIL_NAVEGADOR), **opcoes)
            except ErroPlaywright:
                # O perfil já está aberto por outra instância do MCP (outra sessão do Claude).
                self._perfil_temporario = Path(tempfile.mkdtemp(prefix="jurisprudencia-tse-"))
        return await self._playwright.chromium.launch_persistent_context(str(self._perfil_temporario), **opcoes)

    async def _recarregar(self) -> None:
        await self._pagina.reload(wait_until="domcontentloaded")
        await self._aguardar_portal()

    async def _aguardar_portal(self) -> None:
        await self._pagina.wait_for_selector(_SELETOR_PRONTO, timeout=60_000)
        # Numa página recém-aberta o hCaptcha leva vários segundos para ficar pronto; se a pesquisa
        # sair antes, o token pode passar dos 15 s que o portal espera.
        try:
            await self._pagina.wait_for_function("() => !!window.hcaptcha", timeout=30_000)
        except ErroPlaywright as erro:
            self._precisa_recarregar = True
            raise ErroPortal("O hCaptcha do portal não carregou. Verifique a conexão e tente de novo.") from erro
        self._precisa_recarregar = False

    async def _desafio_visivel(self) -> bool:
        try:
            return bool(await self._pagina.evaluate(_JS_DESAFIO_VISIVEL))
        except ErroPlaywright:
            return False

    async def pesquisar(self, rota: str) -> dict:
        """Dispara a pesquisa descrita em `rota` (fragmento #/...) e devolve o JSON da API."""
        async with self._trava:
            try:
                try:
                    resultado = await self._pesquisar(rota)
                except CaptchaPendente as erro:
                    # Com desafio, a janela já está à vista para o usuário resolver.
                    if erro.desafio_visivel:
                        raise
                    # Prazo estourado sem desafio costuma ser lentidão do hCaptcha: recarrega e tenta
                    # uma única vez, ainda sem mostrar a janela (se um desafio aparecer, ela vem à
                    # frente). Se falhar de novo, mostra a janela para o usuário ver o que houve.
                    try:
                        resultado = await self._pesquisar(rota)
                    except CaptchaPendente:
                        if not self._janela_exibida:
                            await self._exibir_janela()
                        raise
                if self._janela_exibida:
                    await self._ocultar_janela()
                return resultado
            except ErroPlaywright as erro:
                self._precisa_recarregar = True
                raise ErroPortal(f"Falha no navegador: {erro.message.splitlines()[0]}") from erro

    async def _pesquisar(self, rota: str) -> dict:
        await self._garantir_pagina()
        if self._precisa_recarregar:
            await self._recarregar()

        self._falha_captcha = None
        espera = asyncio.ensure_future(
            self._pagina.wait_for_event(
                "response", predicate=_e_resposta_de_pesquisa, timeout=TEMPO_MAXIMO_PESQUISA * 1000
            )
        )
        await self._pagina.evaluate("h => { window.location.hash = h; }", rota)

        desafio = False
        while not espera.done():
            await asyncio.sleep(0.5)
            if not desafio and await self._desafio_visivel():
                desafio = True
                await self._exibir_janela()
            if self._falha_captcha:
                espera.cancel()
                self._precisa_recarregar = True
                raise CaptchaPendente(desafio_visivel=desafio)

        try:
            resposta = espera.result()
        except ErroPlaywright as erro:
            self._precisa_recarregar = True
            if desafio:
                raise CaptchaPendente(desafio_visivel=True) from erro
            raise ErroPortal("O portal não respondeu à pesquisa no tempo esperado.") from erro

        if resposta.status != 200:
            raise ErroPortal(f"A API de pesquisa respondeu HTTP {resposta.status}.")
        return await resposta.json()
