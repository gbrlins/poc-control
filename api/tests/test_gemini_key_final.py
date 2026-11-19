"""chave_final: só os últimos 4 caracteres da chave pessoal, pra Minha conta mostrar qual chave está em uso."""
import os

for chave, valor in {
    "POSTGRES_USER": "x", "POSTGRES_PASSWORD": "x", "POSTGRES_DB": "x", "SESSION_SECRET": "teste",
    "GEMINI_API_KEY": "x", "ADMIN_EMAIL": "a@example.com", "ADMIN_PASSWORD_HASH": "x",
}.items():
    os.environ.setdefault(chave, valor)

from app.crypto import encrypt_secret  # noqa: E402
from app.gemini_key import chave_final  # noqa: E402


class _U:
    def __init__(self, cifrada):
        self.gemini_api_key_encrypted = cifrada


def test_mostra_so_os_quatro_ultimos_caracteres():
    assert chave_final(_U(encrypt_secret("AIzaSyEXEMPLO1234567890"))) == "7890"


def test_sem_chave_ou_sem_usuario_devolve_nulo():
    assert chave_final(None) is None
    assert chave_final(_U(None)) is None


def test_chave_que_nao_descriptografa_devolve_nulo():
    assert chave_final(_U("lixo-que-nao-e-fernet")) is None
