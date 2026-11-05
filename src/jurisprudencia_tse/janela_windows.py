"""Ícone do navegador na barra de tarefas do Windows.

Com a janela fora da tela, o ícone na barra de tarefas é o único sinal visível do navegador. Para
tirá-lo, a janela recebe o estilo de "janela de ferramenta" do Windows; para devolvê-lo (quando o
hCaptcha pede desafio), o estilo é retirado. Isso muda só a aparência na barra de tarefas: o
navegador continua sendo o Edge comum, com janela.

As janelas são achadas pelos processos filhos deste servidor (o Playwright abre o navegador como
neto do Python), então outras janelas do Edge do usuário não são afetadas. Fora do Windows, e em
qualquer falha, as funções não fazem nada.
"""

import os
import sys

_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
_SW_HIDE = 0
_SW_SHOWNOACTIVATE = 4
_SW_SHOW = 5
_CLASSE_JANELA_CHROMIUM = "Chrome_WidgetWin_1"

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]

    class _EntradaProcesso(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    _TH32CS_SNAPPROCESS = 0x2
    _INVALID_HANDLE = wintypes.HANDLE(-1).value
    _CallbackJanela = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _processos_descendentes(raiz: int) -> set[int]:
        instantaneo = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if not instantaneo or instantaneo == _INVALID_HANDLE:
            return set()
        filhos: dict[int, list[int]] = {}
        try:
            entrada = _EntradaProcesso()
            entrada.dwSize = ctypes.sizeof(_EntradaProcesso)
            ok = _kernel32.Process32FirstW(instantaneo, ctypes.byref(entrada))
            while ok:
                filhos.setdefault(entrada.th32ParentProcessID, []).append(entrada.th32ProcessID)
                ok = _kernel32.Process32NextW(instantaneo, ctypes.byref(entrada))
        finally:
            _kernel32.CloseHandle(instantaneo)
        encontrados: set[int] = set()
        fila = [raiz]
        while fila:
            for filho in filhos.get(fila.pop(), []):
                if filho not in encontrados and filho != raiz:
                    encontrados.add(filho)
                    fila.append(filho)
        return encontrados

    def _janelas_do_navegador() -> list:
        processos = _processos_descendentes(os.getpid())
        if not processos:
            return []
        janelas = []

        def visitar(hwnd, _):
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in processos and _user32.IsWindowVisible(hwnd):
                classe = ctypes.create_unicode_buffer(64)
                _user32.GetClassNameW(hwnd, classe, 64)
                if classe.value == _CLASSE_JANELA_CHROMIUM:
                    janelas.append(hwnd)
            return True

        _user32.EnumWindows(_CallbackJanela(visitar), 0)
        return janelas

    def _aplicar(na_barra: bool) -> None:
        for hwnd in _janelas_do_navegador():
            estilo = _user32.GetWindowLongPtrW(hwnd, _GWL_EXSTYLE)
            novo = estilo & ~_WS_EX_TOOLWINDOW if na_barra else estilo | _WS_EX_TOOLWINDOW
            if novo == estilo:
                continue
            # A barra de tarefas só relê o estilo quando a janela é escondida e mostrada de novo.
            _user32.ShowWindow(hwnd, _SW_HIDE)
            _user32.SetWindowLongPtrW(hwnd, _GWL_EXSTYLE, novo)
            _user32.ShowWindow(hwnd, _SW_SHOW if na_barra else _SW_SHOWNOACTIVATE)


def mostrar_na_barra_de_tarefas(mostrar: bool) -> None:
    """Põe (True) ou tira (False) da barra de tarefas as janelas do navegador aberto por este servidor."""
    if sys.platform != "win32":
        return
    try:
        _aplicar(mostrar)
    except Exception:  # noqa: BLE001 - recurso cosmético: nunca deve derrubar a pesquisa
        pass
