"""Handshake OAuth (Authorization Code) para obter o refresh token.

Rodar uma vez e depois a cada ~180 dias. O refresh token do Spotify expira
180 dias após a autorização original, e usar o refresh não estende esse prazo.

    python src/get_refresh_token.py

Passo a passo:
1. Abre o navegador na página de autorização do Spotify.
2. Sobe um servidor HTTP temporário em 127.0.0.1:8888 para receber o
   callback, assim não é preciso copiar o `code` da barra de endereço.
3. Confere o `state` (proteção contra CSRF) e troca o `code` por tokens em
   POST /api/token, com as credenciais do app no header Basic.
4. Grava SPOTIFY_REFRESH_TOKEN e SPOTIFY_REFRESH_TOKEN_ISSUED_AT no .env.
5. Valida com GET /me.
"""

import base64
import secrets
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import dotenv_values, set_key

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
ME_URL = "https://api.spotify.com/v1/me"
SCOPES = "user-read-recently-played user-top-read user-library-read playlist-read-private"
CALLBACK_TIMEOUT_S = 300


def basic_auth_header(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def wait_for_callback(redirect_uri: str) -> dict:
    """Sobe o servidor no host/porta da redirect URI e devolve os parâmetros do callback."""
    parsed = urlparse(redirect_uri)
    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (nome exigido pelo http.server)
            url = urlparse(self.path)
            if url.path != parsed.path:
                self.send_response(404)
                self.end_headers()
                return
            result.update({k: v[0] for k, v in parse_qs(url.query).items()})
            ok = "code" in result
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Pronto, pode fechar esta aba." if ok else f"Erro: {result.get('error')}"
            self.wfile.write(f"<h2>{msg}</h2>".encode())

        def log_message(self, *args):  # silencia o log padrão
            pass

    server = HTTPServer((parsed.hostname, parsed.port), Handler)
    server.timeout = CALLBACK_TIMEOUT_S
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    thread.join()
    server.server_close()
    return result


def main() -> int:
    env = dotenv_values(ENV_PATH)
    client_id = env.get("SPOTIFY_CLIENT_ID")
    client_secret = env.get("SPOTIFY_CLIENT_SECRET")
    redirect_uri = env.get("SPOTIFY_REDIRECT_URI") or "http://127.0.0.1:8888/callback"
    if not client_id or not client_secret:
        print("Preencha SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET no .env primeiro.")
        return 1

    state = secrets.token_urlsafe(16)
    auth_url = AUTHORIZE_URL + "?" + urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
    })
    print("Abrindo o navegador para autorizar. Se não abrir, cole esta URL:\n")
    print(auth_url, "\n")
    webbrowser.open(auth_url)

    params = wait_for_callback(redirect_uri)
    if not params:
        print(f"Nenhum callback recebido em {CALLBACK_TIMEOUT_S}s.")
        return 1
    if "error" in params:
        print(f"Autorização negada: {params['error']}")
        return 1
    if params.get("state") != state:
        print("State não confere — possível CSRF ou callback antigo. Abortando.")
        return 1

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": params["code"],
            "redirect_uri": redirect_uri,  # tem que ser idêntica à do /authorize
        },
        headers={"Authorization": basic_auth_header(client_id, client_secret)},
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"Falha na troca do code: {resp.status_code} {resp.text}")
        return 1
    tokens = resp.json()

    issued_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    set_key(ENV_PATH, "SPOTIFY_REFRESH_TOKEN", tokens["refresh_token"], quote_mode="never")
    set_key(ENV_PATH, "SPOTIFY_REFRESH_TOKEN_ISSUED_AT", issued_at, quote_mode="never")
    print(f"Refresh token gravado no .env (emitido em {issued_at}, vale ~180 dias).")
    print(f"Scopes concedidos: {tokens.get('scope')}")

    me = requests.get(
        ME_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"}, timeout=30
    )
    if me.status_code != 200:
        print(f"GET /me falhou: {me.status_code} {me.text}")
        return 1
    print(f"GET /me OK — olá, {me.json().get('display_name') or me.json().get('id')}!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
