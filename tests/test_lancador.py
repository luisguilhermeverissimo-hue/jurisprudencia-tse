"""Testes do lançador da extensão (mcpb/lancador.py): escolha dos certificados entregues ao uv."""

import importlib.util
import ssl
import sys
from pathlib import Path

import pytest

_CAMINHO = Path(__file__).resolve().parent.parent / "mcpb" / "lancador.py"
_spec = importlib.util.spec_from_file_location("lancador", _CAMINHO)
lancador = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lancador)

PEM_MOZILLA = "-----BEGIN CERTIFICATE-----\nMOZILLA\n-----END CERTIFICATE-----\n"
PEM_WINDOWS = "-----BEGIN CERTIFICATE-----\nWINDOWS\n-----END CERTIFICATE-----\n"


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    monkeypatch.setenv("TSE_PASTA_DADOS", str(tmp_path / "dados"))
    mozilla = tmp_path / "cacert.pem"
    mozilla.write_text(PEM_MOZILLA, encoding="utf-8")
    monkeypatch.setattr(lancador, "CERTIFICADOS_MOZILLA", mozilla)
    monkeypatch.setattr(lancador, "certificados_windows", lambda: [PEM_WINDOWS])
    monkeypatch.setattr(lancador.sys, "platform", "win32")
    return tmp_path


def test_lista_junta_mozilla_e_windows(pasta):
    destino = lancador.preparar_certificados()
    assert destino == pasta / "dados" / "certificados.pem"
    texto = destino.read_text(encoding="utf-8")
    assert PEM_MOZILLA.strip() in texto and PEM_WINDOWS in texto
    assert not list((pasta / "dados").glob("*.tmp"))


def test_lista_igual_nao_e_regravada(pasta):
    destino = lancador.preparar_certificados()
    antes = destino.stat().st_mtime_ns
    assert lancador.preparar_certificados() == destino
    assert destino.stat().st_mtime_ns == antes


def test_lista_muda_quando_o_windows_muda(pasta, monkeypatch):
    lancador.preparar_certificados()
    novo = PEM_WINDOWS.replace("WINDOWS", "NOVO")
    monkeypatch.setattr(lancador, "certificados_windows", lambda: [novo])
    assert novo in lancador.preparar_certificados().read_text(encoding="utf-8")


def test_sem_cacert_nao_ha_lista(pasta, monkeypatch):
    # Claude Code: o lançador roda direto do GitHub, sem o cacert.pem ao lado.
    monkeypatch.setattr(lancador, "CERTIFICADOS_MOZILLA", pasta / "nao-existe.pem")
    assert lancador.preparar_certificados() is None


def test_fora_do_windows_nao_ha_lista(pasta, monkeypatch):
    monkeypatch.setattr(lancador.sys, "platform", "linux")
    assert lancador.preparar_certificados() is None


def test_com_lista_o_uv_recebe_ssl_cert_file(tmp_path):
    ambiente = {"UV_NATIVE_TLS": "true"}
    lancador.configurar_tls(ambiente, tmp_path / "certificados.pem", falha_certificado=False)
    assert ambiente["SSL_CERT_FILE"] == str(tmp_path / "certificados.pem")


def test_ssl_cert_file_do_usuario_e_respeitado(tmp_path):
    ambiente = {"SSL_CERT_FILE": "C:/meu.pem"}
    lancador.configurar_tls(ambiente, tmp_path / "certificados.pem", falha_certificado=True)
    assert ambiente == {"SSL_CERT_FILE": "C:/meu.pem"}


def test_sem_lista_e_windows_reconhecendo_o_github_usa_o_windows():
    ambiente = {}
    lancador.configurar_tls(ambiente, None, falha_certificado=False)
    assert ambiente == {"UV_NATIVE_TLS": "true", "UV_SYSTEM_CERTS": "true"}


def test_sem_lista_e_windows_sem_a_raiz_usa_a_lista_do_uv():
    # Mesmo com UV_NATIVE_TLS gravado pelo usuário (contorno antigo do README), que falharia.
    ambiente = {"UV_NATIVE_TLS": "true", "UV_SYSTEM_CERTS": "true", "OUTRA": "1"}
    lancador.configurar_tls(ambiente, None, falha_certificado=True)
    assert ambiente == {"OUTRA": "1"}


def test_falha_de_certificado_e_reconhecida():
    import urllib.error

    erro = urllib.error.URLError(ssl.SSLCertVerificationError(1, "unable to get local issuer certificate"))
    assert lancador._falha_de_certificado(erro)
    assert not lancador._falha_de_certificado(urllib.error.URLError(TimeoutError("timed out")))


def test_versao_consultada_tem_preferencia(tmp_path, monkeypatch):
    monkeypatch.setenv("TSE_PASTA_DADOS", str(tmp_path))
    monkeypatch.delenv("TSE_VERSAO", raising=False)
    (tmp_path / "versao-em-uso.txt").write_text("v0.3.1", encoding="utf-8")
    assert lancador.escolher_versao("v0.3.2") == ("v0.3.2", True)
    assert lancador.escolher_versao(None) == ("v0.3.2", False)


@pytest.mark.skipif(sys.platform != "win32", reason="lista de certificados do Windows")
def test_certificados_do_windows_sao_lidos():
    pems = lancador.certificados_windows()
    assert pems and all(p.startswith("-----BEGIN CERTIFICATE-----") for p in pems)
    contexto = ssl.create_default_context(cadata="".join(pems))
    assert contexto.cert_store_stats()["x509_ca"] > 0
