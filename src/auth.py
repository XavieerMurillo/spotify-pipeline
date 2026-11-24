"""Autenticação: troca o refresh token por um access token válido.

O handshake inicial (Authorization Code) é feito por `get_refresh_token.py`.
Daqui em diante o pipeline nunca abre navegador: usa grant_type=refresh_token
em POST https://accounts.spotify.com/api/token.

Decisões (ver README):
- Segredos ficam no .env, que está no .gitignore.
- O access token (vale 1 h) é renovado na primeira chamada de cada execução e
  de novo quando faltar menos de REFRESH_MARGIN_S para expirar. Se mesmo assim
  vier 401, `spotify_api` força um refresh e tenta uma vez.
- Se a resposta do refresh trouxer um refresh_token novo, ele é gravado no
  .env. Se não trouxer, o atual continua valendo e nada é sobrescrito.
- O refresh token vence 180 dias após a autorização original, e o refresh não
  estende esse prazo. Por isso a data de emissão fica no .env e o script avisa
  quando o vencimento estiver próximo.
"""

import base64
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import dotenv_values, set_key

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
TOKEN_URL = "https://accounts.spotify.com/api/token"

REFRESH_MARGIN_S = 300
REFRESH_TOKEN_LIFETIME = timedelta(days=180)
EXPIRY_WARNING = timedelta(days=15)
REQUIRED_KEYS = ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REFRESH_TOKEN")

log = logging.getLogger(__name__)

# Cache em memória: vale só durante a execução do processo.
_cache: dict = {"access_token": None, "expires_at": 0.0}


class AuthError(RuntimeError):
    """Falha de autenticação que exige ação manual (ex.: refazer o handshake)."""


def _load_env() -> dict:
    env = dotenv_values(ENV_PATH)
    missing = [k for k in REQUIRED_KEYS if not env.get(k)]
    if missing:
        raise AuthError(
            f"Faltando no .env: {', '.join(missing)}. "
            "Rode `python src/get_refresh_token.py` para gerar o refresh token."
        )
    return env


def _warn_if_expiring(issued_at: str | None) -> None:
    if not issued_at:
        log.warning("SPOTIFY_REFRESH_TOKEN_ISSUED_AT ausente: não dá para prever o vencimento.")
        return
    expires = datetime.fromisoformat(issued_at) + REFRESH_TOKEN_LIFETIME
    remaining = expires - datetime.now(timezone.utc)
    if remaining <= EXPIRY_WARNING:
        log.warning(
            "Refresh token vence em %s dia(s) (%s). Rode `python src/get_refresh_token.py`.",
            max(remaining.days, 0),
            expires.date().isoformat(),
        )


def _refresh(env: dict) -> None:
    basic = base64.b64encode(
        f"{env['SPOTIFY_CLIENT_ID']}:{env['SPOTIFY_CLIENT_SECRET']}".encode()
    ).decode()
    resp = requests.post(
        TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": env["SPOTIFY_REFRESH_TOKEN"]},
        headers={"Authorization": f"Basic {basic}"},
        timeout=30,
    )

    if resp.status_code == 400:
        try:
            error = resp.json().get("error")
        except ValueError:
            error = None
        if error == "invalid_grant":
            # A doc manda não tentar de novo: o token venceu ou foi revogado.
            raise AuthError(
                "Refresh token inválido ou vencido (invalid_grant). "
                "Rode `python src/get_refresh_token.py` para autorizar de novo."
            )
    if resp.status_code in (400, 401):
        raise AuthError(f"Falha no refresh ({resp.status_code}): {resp.text}")
    resp.raise_for_status()

    data = resp.json()
    _cache["access_token"] = data["access_token"]
    _cache["expires_at"] = time.time() + int(data.get("expires_in", 3600))

    new_refresh = data.get("refresh_token")
    if new_refresh and new_refresh != env["SPOTIFY_REFRESH_TOKEN"]:
        # A data de emissão não muda: a rotação não estende os 180 dias.
        set_key(ENV_PATH, "SPOTIFY_REFRESH_TOKEN", new_refresh, quote_mode="never")
        log.info("Spotify devolveu um refresh token novo; .env atualizado.")


def get_access_token(force_refresh: bool = False) -> str:
    """Devolve um access token válido, renovando quando necessário."""
    fresh = _cache["access_token"] and time.time() < _cache["expires_at"] - REFRESH_MARGIN_S
    if fresh and not force_refresh:
        return _cache["access_token"]

    env = _load_env()
    _warn_if_expiring(env.get("SPOTIFY_REFRESH_TOKEN_ISSUED_AT"))
    _refresh(env)
    return _cache["access_token"]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    get_access_token()
    expires = datetime.fromtimestamp(_cache["expires_at"], timezone.utc)
    print(f"Access token OK, válido até {expires.isoformat(timespec='seconds')}.")
