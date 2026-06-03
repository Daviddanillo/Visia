"""Limitador de requisições (proteção contra força bruta no login).

Usa slowapi (armazenamento em memória por processo). Em hospedagens atrás de
proxy reverso — como o Render —, o IP real do cliente chega no cabeçalho
``X-Forwarded-For``; por isso a chave usa o primeiro IP dele quando presente,
caindo para o IP da conexão quando não há proxy.
"""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _client_key(request: Request) -> str:
    encaminhado = request.headers.get("x-forwarded-for")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_client_key)
